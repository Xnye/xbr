# -*- coding: utf-8 -*-
"""
build_grammar_deep.py — 生成 data/grammar_deep.json

把 content/grammar_l*.py 里手写的深度讲义编译成前端可直接消费的数据：
  * 例句的 ! 标注明文 → clean / ruby / romaji 三种形态（罗马音从假名注音直转，
    不复用 lessons.json 里 pykakasi 生成的字段——那一版存在误读，如「李(り)」被转成 sumomo）
  * 与 lessons.json 的语法条目做双向校验，确保覆盖课程内教材语法点一条不漏、一条不多
  * 校验 related / xid 引用不悬空

用法：python build_grammar_deep.py
"""

import io
import json
import os
import sys
import importlib

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, 'content'))

import morphology as M  # noqa: E402

LESSONS_PATH = os.path.join(HERE, 'data', 'lessons.json')
EXEMPLARS_PATH = os.path.join(HERE, 'data', 'exemplars.json')
OUT_PATH = os.path.join(HERE, 'data', 'grammar_deep.json')

# 自动发现 content/grammar_lN.py。扩课时只新增模块，不再手工维护 import/SOURCES。
# --through N 只编译到第 N 课，便于分批验证，不影响默认全量构建。
_through = 48
if '--through' in sys.argv:
    _through = int(sys.argv[sys.argv.index('--through') + 1])
SOURCES = []
for _n in range(1, _through + 1):
    _name = 'grammar_l%d' % _n
    try:
        _mod = importlib.import_module(_name)
    except ModuleNotFoundError as exc:
        if exc.name == _name:
            continue
        raise
    SOURCES.append((_n, _mod.ENTRIES))


def compile_example(ex):
    """把一条例句的标注明文编译成 clean / ruby / romaji。"""
    r = M.render_text(ex['annot'])
    out = {
        'jp': r['clean'],
        'jp_ruby': r['ruby'],
        'romaji': r['romaji'],
        'zh': ex.get('zh', ''),
        'lit': ex.get('lit', ''),
        'src': ex.get('src', ''),
    }
    if ex.get('xid'):
        out['xid'] = ex['xid']
    if ex.get('note'):
        out['note'] = ex['note']
    return out


def compile_entry(e):
    out = dict(e)
    out['examples'] = [compile_example(x) for x in e.get('examples', [])]
    return out


def main():
    with io.open(LESSONS_PATH, encoding='utf-8') as f:
        lessons = json.load(f)

    exemplar_ids = set()
    if os.path.exists(EXEMPLARS_PATH):
        with io.open(EXEMPLARS_PATH, encoding='utf-8') as f:
            exemplar_ids = {x['id'] for x in json.load(f)}

    entries = []
    for lesson_num, src in SOURCES:
        entries.extend(compile_entry(e) for e in src)

    # ---------------- 校验 0：讲义结构完整 ----------------
    for e in entries:
        eid = e['id']
        if e.get('concept'):
            continue
        assert e.get('essence'), '%s 缺 essence' % eid
        assert e.get('formula', {}).get('template'), '%s 缺 formula.template' % eid
        assert e.get('why'), '%s 缺 why' % eid
        assert len(e.get('examples') or []) >= 2, '%s 例句少于 2 条' % eid
        assert len(e.get('pitfalls') or []) >= 2, '%s 易错对照少于 2 条' % eid
        assert len(e.get('self_check') or []) >= 2, '%s 自检少于 2 题' % eid
        assert len(e.get('answers') or []) >= len(e.get('self_check') or []), '%s 答案少于自检题' % eid
        assert '~' not in e.get('pattern', ''), '%s pattern 用了 ASCII ~' % eid
        blob = json.dumps(e, ensure_ascii=False)
        assert 'TODO' not in blob and '待补' not in blob, '%s 含占位文本' % eid

    # ---------------- 校验 1：id 唯一 ----------------
    ids = [e['id'] for e in entries]
    dup = {i for i in ids if ids.count(i) > 1}
    assert not dup, '重复的讲义 id: %s' % dup

    # ---------------- 校验 2：与教材语法点双向对齐 ----------------
    book = {}
    for les in lessons:
        n = les['number']
        if n not in dict(SOURCES):
            continue
        for g in les.get('grammar') or []:
            book[(n, str(g['idx']))] = g['expression']

    mine = {(e['lesson'], str(e['idx'])): e['pattern']
            for e in entries if not e.get('concept')}

    missing = sorted(set(book) - set(mine))
    extra = sorted(set(mine) - set(book))
    if missing:
        print('!! 教材有、讲义缺：')
        for k in missing:
            print('     第%d课 idx=%s  %s' % (k[0], k[1], book[k]))
    if extra:
        print('!! 讲义有、教材无（idx 写错？）：')
        for k in extra:
            print('     第%d课 idx=%s  %s' % (k[0], k[1], mine[k]))
    assert not missing and not extra, '教材语法点与讲义未对齐'

    # ---------------- 校验 3：related / xid 引用不悬空 ----------------
    # 指向已覆盖课程（L1_～L4_）的引用必须真实存在，写错就是断链；
    # 指向后续课程的引用是"预告"，扩课后自动消解，只统计不报错。
    idset = set(ids)
    covered_prefixes = tuple('L%d_' % n for n in dict(SOURCES))
    broken = [(e['id'], r) for e in entries
              for r in e.get('related', [])
              if r.startswith(covered_prefixes) and r not in idset]
    forward = [r for e in entries for r in e.get('related', []) if r not in idset]
    if broken:
        for eid, r in broken:
            print('!! %s 引用了不存在的已覆盖条目: %s' % (eid, r))
    assert not broken, 'related 引用断链'

    bad_xid = []
    for e in entries:
        for x in e.get('examples', []):
            xid = x.get('xid')
            if xid and xid not in exemplar_ids:
                bad_xid.append((e['id'], xid))
    if bad_xid and exemplar_ids:
        print('!! 例句引用的透视图 id 尚不存在（先跑 build_exemplars_auto.py）：')
        for eid, xid in bad_xid:
            print('     %s -> %s' % (eid, xid))

    # ---------------- 校验 4：例句渲染产物完整 ----------------
    for e in entries:
        for x in e['examples']:
            for k in ('jp', 'jp_ruby', 'romaji', 'zh'):
                assert x.get(k), '%s 例句缺字段 %s: %s' % (e['id'], k, x)
            assert '　' not in x['romaji'], '%s 罗马音混入全角空格: %s' % (e['id'], x['romaji'])

    # ---------------- 统计与输出 ----------------
    entries.sort(key=lambda e: (e['lesson'], e.get('order', 99)))

    # 先量正文字数，再加派生字段，免得统计被 related_resolved 灌水
    total_chars = sum(len(json.dumps(e, ensure_ascii=False)) for e in entries)
    legacy_chars = sum(len(g['explanation'])
                       for les in lessons for g in (les.get('grammar') or [])
                       if les['number'] in dict(SOURCES))

    # related 解析成可点击的链接数据；指向后续课程的保留 id 并标记 pending
    by_id = {e['id']: e for e in entries}
    for e in entries:
        resolved = []
        for r in e.get('related', []):
            tgt = by_id.get(r)
            if tgt:
                resolved.append({'id': r, 'label': tgt['pattern'], 'lesson': tgt['lesson'],
                                 'category': tgt.get('category', '')})
            else:
                resolved.append({'id': r, 'label': r.split('_', 1)[1], 'pending': True})
        e['related_resolved'] = resolved

    doc = {
        'meta': {
            'version': 2,
            'coverage': sorted(dict(SOURCES).keys()),
            'entry_count': len(entries),
            'example_count': sum(len(e.get('examples', [])) for e in entries),
            'pitfall_count': sum(len(e.get('pitfalls', [])) for e in entries),
            'note': '深度语法讲义。取代 lessons.json 里抓取来的碎片式 explanation（中位数40字）。',
        },
        'particle_kb': {k: {'color': v['color'], 'name': v['name'], 'desc': v['desc']}
                        for k, v in M.PARTICLES.items()},
        'entries': entries,
    }

    with io.open(OUT_PATH, 'w', encoding='utf-8') as f:
        json.dump(doc, f, ensure_ascii=False, indent=2)

    print('已生成 %s' % OUT_PATH)
    print('  覆盖课程   : %s' % doc['meta']['coverage'])
    print('  讲义条数   : %d（教材语法点全覆盖）' % len(entries))
    print('  例句总数   : %d' % doc['meta']['example_count'])
    print('  易错对照   : %d 组' % doc['meta']['pitfall_count'])
    print('  正文体量   : %d 字（原碎片式解释合计 %d 字，放大 %.1f 倍）'
          % (total_chars, legacy_chars, total_chars / max(legacy_chars, 1)))
    if forward:
        print('  跨课预告   : %d 处 related 指向后续课程（扩课后自动消解）' % len(forward))
    if bad_xid:
        print('  待补透视图 : %d 处例句引用了尚未生成的 xid' % len(bad_xid))
        for eid, xid in bad_xid[:20]:
            print('       %s -> %s' % (eid, xid))


if __name__ == '__main__':
    main()
