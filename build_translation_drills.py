# -*- coding: utf-8 -*-
"""
build_translation_drills.py — 生成 data/translation_drills.json

中翻日练习：把 data/grammar_deep.json 里每条讲义自带的课文原句（jp ＋ zh），
按「考点」重新打包成「看中文，写日语」的练习卡。

两条设计约束：
  * 句数由考点数决定：每课句数 ≈ 3 × 该课语法考点数（考点多的课自动多练，
    不写死每课固定多少句）。同一课内按句子体量由短到长分成 热身／进阶／挑战 三级，
    所以任何一课点开都是「从简到难」，而不是把 30 句一股脑倒出来。
  * 答案为教材原句，带振假名、罗马音、出处与考点标记；有透视图（xid）的句子
    还能就地展开结构图，保证「翻错了知道错在哪」。

用法：python build_translation_drills.py
"""

import io
import json
import os
import re
import sys

sys.stdout.reconfigure(encoding='utf-8')

HERE = os.path.dirname(os.path.abspath(__file__))
DEEP_PATH = os.path.join(HERE, 'data', 'grammar_deep.json')
OUT_PATH = os.path.join(HERE, 'data', 'translation_drills.json')

# 三级分档的累计切点：前 40% 热身，接下来 32% 进阶，其余挑战。
TIER_CUTS = (0.40, 0.72)

# 体量打分里额外加权的语法特征：出现一处就算「这句不简单」。
HARD_PATTERN = re.compile(
    r'(ながら|ので|のに|たら|ても|ば、|させる|られる|ておく|てある|てしまう|'
    r'ようになる|ようにする|しか|ばかり|はず|らしい|みたい|そうな|そうに)'
)

# 中文题干里的半角括号统一成全角：混排时（您）比(您)更像中文正文。
_ASCII_PAREN = re.compile(r'\(([^()]*)\)')


def clean_zh(zh):
    s = (zh or '').strip()
    s = _ASCII_PAREN.sub(r'（\1）', s)
    return s


def tier_cuts(n):
    """返回 (tier1 结束位置, tier2 结束位置)；保证每档至少一句。"""
    if n <= 1:
        return 1, 1
    c1 = max(1, int(round(n * TIER_CUTS[0])))
    c2 = max(c1 + 1, int(round(n * TIER_CUTS[1])))
    if c2 > n:
        c2 = n
    if c2 <= c1:
        c1 = max(1, c2 - 1)
    return c1, c2


def dedup_key(jp):
    """去重键：抹掉标点与空白只比正文。
    教材里同一句话在不同考点会换一种标点引用（はい、小野です／はい，小野です），
    按原文比较会漏掉，练习里就出现两条一模一样的题干。
    """
    return re.sub(r'[。．！？、，,.　\s]', '', jp)



def weight(jp):
    """句子体量：字数为主，分句与复杂句式加权，只用来给同字数的句子排序。"""
    bare = re.sub(r'[。！？、，　\s]', '', jp)
    body = re.sub(r'[。！？]\s*$', '', jp)
    clauses = len(re.findall(r'[、，。]', body))
    w = len(bare) + clauses * 6
    if HARD_PATTERN.search(jp):
        w += 4
    return w


def char_len(jp):
    """纯字数：练习里「由简到难」的第一判据，也是前端标注字数区间的口径。"""
    return len(re.sub(r'[。！？、，　\s]', '', jp))


def main():
    with io.open(DEEP_PATH, encoding='utf-8') as f:
        deep = json.load(f)

    by_lesson = {}
    for e in deep['entries']:
        by_lesson.setdefault(e['lesson'], []).append(e)

    lessons = {}
    dropped = 0
    for num in sorted(by_lesson):
        entries = sorted(by_lesson[num], key=lambda e: (e.get('order', 99)))
        points = [{
            'id': e['id'],
            'pattern': e['pattern'],
            'category': e.get('category', ''),
        } for e in entries]

        raw = []
        seen = set()
        for e in entries:
            for x in e.get('examples') or []:
                jp = x.get('jp') or ''
                zh = clean_zh(x.get('zh'))
                if not jp or not zh:
                    continue
                # 同一课里同一句会被不同考点重复引用，只保留第一次出现的归属
                key = dedup_key(jp)
                if key in seen:
                    dropped += 1
                    continue
                seen.add(key)
                item = {
                    'tier': 0,
                    'zh': zh,
                    'jp': jp,
                    'jp_ruby': x.get('jp_ruby') or jp,
                    'romaji': x.get('romaji') or '',
                    'point': e['pattern'],
                    'point_id': e['id'],
                    'category': e.get('category', ''),
                    'src': x.get('src', ''),
                    '_chars': char_len(jp),
                    '_w': weight(jp),
                }
                if x.get('xid'):
                    item['xid'] = x['xid']
                raw.append(item)

        if not raw:
            continue

        # 由简到难：先按字数，字数相同再按分句与句式加权。
        # 判据必须是字数：前端在档位标题上标的就是字数区间，
        # 若排序另用一套加权口径，就会出现「进阶档平均比热身档还短」。
        raw.sort(key=lambda it: (it['_chars'], it['_w']))
        c1, c2 = tier_cuts(len(raw))
        items = []
        for i, it in enumerate(raw):
            it['tier'] = 1 if i < c1 else (2 if i < c2 else 3)
            it['id'] = 'l%d_t%02d' % (num, i + 1)
            it['chars'] = it.pop('_chars')
            it.pop('_w', None)
            items.append(it)


        counts = [sum(1 for it in items if it['tier'] == t) for t in (1, 2, 3)]
        lessons[str(num)] = {
            'points': points,
            'point_count': len(points),
            'item_count': len(items),
            'tier_counts': counts,
            'items': items,
        }

    # ---------------- 校验 ----------------
    assert lessons, '没有生成任何练习数据'
    total = 0
    for num, les in lessons.items():
        n = int(num)
        assert les['items'], '第 %d 课没有练习句' % n
        # 句数下限：考点越多，练得越多（每考点至少 2 句）
        assert les['item_count'] >= les['point_count'] * 2, \
            '第 %d 课练习句少于考点的两倍' % n
        assert sum(les['tier_counts']) == les['item_count'], '第 %d 课分档统计不符' % n
        assert les['tier_counts'][0] >= 1 and les['tier_counts'][-1] >= 1, \
            '第 %d 课有空档' % n
        zhs = [it['zh'] for it in les['items']]
        assert len(zhs) == len(set(zhs)), '第 %d 课有重复题干' % n

        prev = 0
        tier_prev_len = {1: 0, 2: 0, 3: 0}
        for it in les['items']:
            for k in ('id', 'zh', 'jp', 'jp_ruby', 'romaji', 'point', 'tier'):
                assert it.get(k), '第 %d 课 %s 缺字段 %s' % (n, it.get('id'), k)
            assert '\uff66' not in it['jp'], '第 %d 课 %s 含半角片假名' % (n, it['id'])
            assert it['chars'] == char_len(it['jp']), '第 %d 课 %s 字数不符' % (n, it['id'])
            # 分档必须单调：热身在前、挑战在后
            assert it['tier'] >= prev, '第 %d 课 %s 分档乱序' % (n, it['id'])
            # 档内句长也必须单调：档位标题标的字数区间要真的递增
            assert it['chars'] >= tier_prev_len[it['tier']], \
                '第 %d 课 %s 档内句长倒挂' % (n, it['id'])
            tier_prev_len[it['tier']] = it['chars']
            prev = it['tier']
        total += les['item_count']

    doc = {
        'meta': {
            'version': 1,
            'lesson_count': len(lessons),
            'item_count': total,
            'note': '中翻日练习：课文原句按考点打包，课内按体量由简到难分三档。',
            'tiers': [
                {'tier': 1, 'label': '热身', 'sub': '短句，先把句型对准'},
                {'tier': 2, 'label': '进阶', 'sub': '多了修饰成分或第二个分句'},
                {'tier': 3, 'label': '挑战', 'sub': '长句、多分句或敬语体'},
            ],
        },
        'lessons': lessons,
    }

    with io.open(OUT_PATH, 'w', encoding='utf-8') as f:
        json.dump(doc, f, ensure_ascii=False, indent=1)

    size = os.path.getsize(OUT_PATH) / 1024.0
    print('已生成 %s（%.0f KB）' % (OUT_PATH, size))
    print('  覆盖课程 : %d 课' % len(lessons))
    print('  练习句数 : %d 句（去重丢弃 %d 句）' % (total, dropped))
    print('  每课句数 : %d ~ %d 句，均值 %.1f'
          % (min(l['item_count'] for l in lessons.values()),
             max(l['item_count'] for l in lessons.values()),
             total / float(len(lessons))))
    print('  每考点句 : %.2f 句' % (total / float(sum(l['point_count'] for l in lessons.values()))))
    xid = sum(1 for l in lessons.values() for it in l['items'] if it.get('xid'))
    print('  带结构图 : %d 句（%.0f%%）' % (xid, 100.0 * xid / total))

    short = sorted(lessons.items(), key=lambda kv: kv[1]['item_count'])[:3]
    long_ = sorted(lessons.items(), key=lambda kv: kv[1]['item_count'])[-3:]
    print('  最短三课 : %s' % '、'.join('第%s课 %d句/%d考点' % (k, v['item_count'], v['point_count'])
                                     for k, v in short))
    print('  最长三课 : %s' % '、'.join('第%s课 %d句/%d考点' % (k, v['item_count'], v['point_count'])
                                     for k, v in long_))


if __name__ == '__main__':
    main()
