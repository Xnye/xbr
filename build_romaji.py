# -*- coding: utf-8 -*-
"""
build_romaji.py — 全 48 课罗马音数据层

为什么要有这个脚本：
  lessons.json 里的 romaji / title_romaji 是 pykakasi 对汉字整句转换的产物，
  实测是错的：李(り) 读成 sumomo、は 读成 ha、へ 读成 he、行きます 写成 iki masu。
  该项目自己定的规矩是「绝对不要使用这两个字段」，罗马音必须由 content/annot.py
  从教材的假名注音重新生成。但前端课文视图一直在读它们，所以这里生成一份
  data/romaji.json，前端只读这份。

输出：
  {
    'meta':      {...},
    'sentences': { jp_raw: {'romaji': str, 'ruby': str?} },   # ruby 只在与教材原注不一致时给
    'words':     { word_clean: romaji },
    'titles':    { title_clean: romaji },
  }

用法：python build_romaji.py        # 生成 + 自检（问题会 exit 1）
      python build_romaji.py --check  # 只自检，不写文件（审计器会调用它）
"""

import io
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, 'content'))

import annot as A        # noqa: E402
import morphology as M   # noqa: E402

LESSONS_PATH = os.path.join(HERE, 'data', 'lessons.json')
OUT_PATH = os.path.join(HERE, 'data', 'romaji.json')
EXEMPLARS_PATH = os.path.join(HERE, 'data', 'exemplars.json')

# ============================================================ 教材数据的修订
# 教材 jp_raw 有两类问题，都会让学习者读到／看到错的日语：
#   ① 漏注音或注错的读音（有教材自己的词汇表或同书其他句子作反证）
#   ② 句子正文／注音的错字（如 起きましか、帰(かぇ)り）
# 这里修的是「生成罗马音、振假名、朗读文本的那一份副本」：
#   前端据此显示正确的日语与振假名，lessons.json 本身保持只读。
# 判据一律是「同一教材里同样的写法怎么写」——不是我们替教材改读音。
SOURCE_PATCHES = (
    # 第32课写作 晴(は)れ，第10课这句注成了 ほ；教材词表也写 はれ@2 → は
    ('!晴(ほ)れ', '!晴(は)れ'),
    # 第14/15/21课另有 5 处 後(あと)で，第21课这句注成了 ご；词表 あとで@1 → あと
    ('!後(ご)で', '!後(あと)で'),
    # 五種類＝ごしゅるい；原文漏了 五 的注音
    ('五!種類(しゅるい)', '!五(ご)!種類(しゅるい)'),
    # 一度＝いちど；原文漏了 一 的注音（第46、48课各一处）
    ('一!度(ど)', '!一(いち)!度(ど)'),
    # 全书 14 处写作 帰(かえ)り，第6课这句注成了 かぇ
    ('!帰(かぇ)り', '!帰(かえ)り'),
    # 第5课正文误抄：应为 起きますか（同页另一句正确写作 起きました）
    ('!起(お)きましか', '!起(お)きますか'),
    # 北京：全书其余 3 处都写 ペキン，第6课这句混用了平假名 ぺ
    ('!北京(ぺキン)', '!北京(ペキン)'),
    # 北京支社＝ペキンししゃ；第5课应用课文把 ペ 写成了平假名 ぺ
    # （与下面 北京(ぺキン) 同一类，由审计器 C16 的平／片假名混用检查找出来）
    ('!北京支社(ぺキンししゃ)', '!北京支社(ペキンししゃ)'),
    # お母さん＝おかあさん；全书另 2 处写作 かあ
    ('お!母(かぁ)さん', 'お!母(かあ)さん'),
    # 行く 的 い 被写成小写 ぃ（全书 3 处：第10课「行(ぃ)きました」、
    # 第19・22课「行(ぃ)かない」——由审计器 C15 的注音一致性扫描找齐）
    ('!行(ぃ)', '!行(い)'),
    # 一皿＝ひとさら；原文注成了 ひょ
    ('!１(ひょ)!皿(さら)', '!１(ひと)!皿(さら)'),
    # ３日間＝みっかかん；原文把 ３ 注成了 みつ，且 ! 把 ３ 和 日間 切成了两块
    ('３(みつ)!日間(かかん)', '３日間(みっかかん)'),
    # ３日＝みっか；同样被 ! 切成两块，促音要连起来才是 mikkadake
    ('!３(みっ)!日(か)だけ', '!３日(みっか)だけ'),
    # 一杯＝いっぱい（促音便）；第13课同页另一句写作 1(いっ)!杯(ぱい)，这句注成了 はい。
    ('!一(いっ)!杯(はい)', '!一(いっ)!杯(ぱい)'),
    # 上海＝シャンハイ；第6课这句的 イ 被写成小写 ィ（与 行(ぃ) 同类的小写假名错字，
    # 同样是审计器 C15 的注音一致性扫描找出来的：全书另 10 处都写 シャンハイ）
    ('!上海(シャンハィ)', '!上海(シャンハイ)'),
    # 一週間＝いっしゅうかん（促音便）；第13课这句注成了 いちしゅうかん。
    # 判据：一＋週間 是促音便组合（一層 いっそう／一回 いっかい 同理），
    # 且全书另两处 一週間 都用于同一句型（本句是唯一写错的一处）。
    ('!一週間(いちしゅうかん)', '!一週間(いっしゅうかん)'),
    # 第16课基本课文正文误抄：应为「…練習しましたが，まだ　あまり　できません」。
    # 判据：本课语法点就是「まだ＋否定＝还没…」，句中的 まで 是"到…为止"，
    # 与 できません 搭配不通；同句 zh 译文也写"但还不太会用"。
    ('が，まで　あまり', 'が，まだ　あまり'),
    # 教材数据里的正文讹抄（与上面的注音错字同类，只报不拦的那套检查找出来的）：
    #   第1课应用课文「はじめましで，」应为 はじめまして
    ('はじめましで', 'はじめまして'),
    #   第8课应用课文「たつた　今」应为 たった今
    ('たつた　!今(いま)', 'たった　!今(いま)'),
    ('たつた　今', 'たった　今'),
    #   第19课应用课文「心配しないて　ください」应为 しないで
    ('心配しないて　ください', '心配しないで　ください'),
    #   第20课应用课文「じゃあ，いっか　ごちそうして」应为 いつか（一階 いっかい 是注音，不在此列）
    ('じゃあ，いっか　ごちそう', 'じゃあ，いつか　ごちそう'),
    # 第23课基本课文正文误抄：教材这处写作 にほんじん（平假名），应为 日本人。
    # 判据：全书 4 处 日本人 都写汉字（第1课基本课文 林さんは 日本人ですか 同款），
    # 且同句前半的 中国人 也写汉字——这一处与 まで/まだ 属同一类讹抄。
    # 下册正文讹抄（与上面同类；判据一律是"同一教材里同样的写法怎么写"）：
    #   第31课应用课文：长音符写成了全角连字符 U+FF0D
    #   （第22课会话里的 ３４９３－３９４５ 是真连字符，不能动）
    ('メ－トル', 'メートル'),
    ('スポ－ツセンター', 'スポーツセンター'),
    # 下册还有一类讹抄：注解把一个**复合词**切成两块注音
    #（遊園/地、会議/室、英字/新聞…），分词器只能拿到两个不存在的碎片。
    # 判据：这些词在教材里是一个词，全书其他地方都整体注音。
    ('!宅配(たくはい)!便(びん)', '!宅配便(たくはいびん)'),
    ('!遊園(ゆうえん)!地(ち)', '!遊園地(ゆうえんち)'),
    ('!会議(かいぎ)!室(しつ)', '!会議室(かいぎしつ)'),
    ('!英字(えいじ)!新聞(しんぶん)', '!英字新聞(えいじしんぶん)'),
    ('!２０１０(にせんじゅう)!年(ねん)', '!２０１０年(にせんじゅうねん)'),
    ('!冷凍(れいとう)!食品(しょくひん)', '!冷凍食品(れいとうしょくひん)'),
    #   日本＝にほん：这里被切成 日(にち)!本(ほん)，读法也跟着错了
    ('!日(にち)!本(ほん)らしい', '!日本(にほん)らしい'),
    #   ３日＝みっか：前面那条只把 ! 挪了位置，还得把注音合并成一个词
    #   （３日 的合并已在上面的条目里一次做完，这里不再重复）
    ('プ－ル', 'プール'),
    #   第41课基本课文：小鳥にげられました → 缺词界（小鳥に／にげられました 两个语块被粘在一起）
    # 下册"缺词界"的 5 处（两个词粘在一起、又都没有 ! 标记）——补一个全角空格即可，
    # 它们是本轮引擎收口后仅剩的 5 处自检命中（都是数据层问题，引擎无从下手）。
    ('!買(か)ったＣＤを', '!買(か)った　ＣＤを'),
    ('!森(もり)さんはお!年寄(としよ)り', '!森(もり)さんは　お!年寄(としよ)り'),
    ('!吸(す)うな」という!意味(いみ)', '!吸(す)うな」　という!意味(いみ)'),
    # 上面那几处补了词界之后，同一语块里还粘着的地方一起补齐（全角空格＝语块分隔）
    ('っていた!小鳥(ことり)', 'っていた　!小鳥(ことり)'),
    ('」　という!意味(いみ)', '」　という　!意味(いみ)'),
    ('お!荷物(にもつ)は!私(わたくし)がお!持(も)ちします', 'お!荷物(にもつ)は　!私(わたくし)が　お!持(も)ちします'),
    # 上面几处用「短模式」再兜一遍：长模式会被更早的补丁改掉，匹配不到（第29/41课）
    ('さんは!飼(か)っていた', 'さんは　!飼(か)っていた'),
    ('マークは「', 'マークは　「'),
    ('!陳(ちん)さんは!飼(か)っていた!小鳥(ことり)', '!陳(ちん)さんは　!飼(か)っていた!小鳥(ことり)'),
    ('!私(わたくし)がお!持(も)ちします', '!私(わたくし)が　お!持(も)ちします'),
    ('!小鳥(ことり)にげられました', '!小鳥(ことり)に　にげられました'),
    # 上面两条是"正文级"订正（多了一个词/少了一个词），jp_clean 也要跟着订正，
    # 同样"缺词界"的 4 处（下册，两个语块之间既没有 ! 也没有全角空格）——
    # 补上语块界之后，助词（を）才能留在它该在的语块里，而不是被吞进整块。
    ('!森(もり)さんはお!年寄(としよ)りの!荷物(にもつ)を!持(も)ってあげました。',
     '!森(もり)さんは　お!年寄(としよ)りの　!荷物(にもつ)を　!持(も)ってあげました。'),
    # 上面几处补丁要按"当前文本"写模式（前一条补丁已经改过那段文字，长模式会匹配不到）
    ('さんは　お!年寄(としよ)りの!荷物(にもつ)を!持(も)',
     'さんは　お!年寄(としよ)りの　!荷物(にもつ)を　!持(も)'),
    ('!馬(ば)さんはとても!上手(じょうず)にレポートを',
     '!馬(ば)さんは　とても　!上手(じょうず)に　レポートを'),
    ('目覚(めざ)ましをかけておいた', '目覚(めざ)ましを　かけておいた'),
    ('このケーキはとてもおいしそうです', 'このケーキは　とても　おいしそうです'),
    ('かけておいたのに，', 'かけておいた　のに，'),
    ('たまにフリーズすることがあります', 'たまに　フリーズすることがあります'),
    ('レポートをまとめました', 'レポートを　まとめました'),
    ('!眼鏡(めがね)をかけて!本(ほん)を!読(よ)みます。',
     '!眼鏡(めがね)を　かけて　!本(ほん)を　!読(よ)みます。'),
    ('!目覚(めざ)ましをかけておいたのに', '!目覚(めざ)ましを　かけておいたのに'),
    # 否则审计 C10「句面与教材一致」会报不一致（C10 比的是渲染后的句面）。
    ('小鳥にげられました', '小鳥に　にげられました'),
    ('書類完成させなければ', '書類を完成させなければ'),
    #   第46课基本课文：この書類完成させなければ… → 掉了宾格助词 を
    ('!書類(しょるい)!完成(かんせい)させなければ', '!書類(しょるい)を!完成(かんせい)させなければ'),
    #   第47课基本课文：注音「め　あ」里夹了全角空格 → めしあ
    ('!召し上(め　あ)がりますか', '!召し上(めしあ)がりますか'),
    ('だったり　にほんじんだったり', 'だったり　!日本人(にほんじん)だったり'),
)


# 课文里夹着的汉语原文（“再见！”“来，来！”“请”……）不是日语，注音层没有读音，
# 罗马音里只能去掉；留着会变成罗马音行中间的汉字。
_CJK = re.compile(r'[\u3400-\u4dbf\u4e00-\u9fff]+')
# 汉语引号（“ ”）去掉；日语引号「」保留，它标的是日文引用
_CN_QUOTE = re.compile(r'[\u201c\u201d]')

# 词表里以 は 收尾的固定表达：这里的 は 是助词，读 wa。
# （其余以 は 收尾的词表条目是 母＝はは、歯＝は、葉＝は 这类实词，读 ha。）
WORD_WA = {
    'こんにちは': 'konnichiwa',
    'こんばんは': 'konbanwa',
    'では': 'dewa',
    'それでは': 'soredewa',
    '実は': 'jitsu wa',
}

_RUBY = re.compile(r'<ruby>(.*?)<rt>(.*?)</rt></ruby>')


def sentence_entry(raw):
    """一句课文 → {'romaji': …, 修订过时再给 'ruby' 与 'clean'}"""
    patched, changed = patch_raw(raw)
    rendered = M.render_text(patched)
    entry = {'romaji': clean_romaji(M.analyze_sentence(patched)['romaji'])}
    if changed:
        # 修订过的句子：振假名与朗读文本都用修订版，前端优先取这两个字段
        star = raw.lstrip().startswith('*')
        entry['ruby'] = ('* ' if star else '') + rendered['ruby']
        entry['clean'] = ('* ' if star else '') + rendered['clean']
    return entry


_LEAD_MARK = re.compile(r'^\*\s*')


def _fix_half_width_spaces(raw):
    """句中的半角空格 → 全角空格。

    判据：全书词与词之间一律用全角空格（U+3000），半角空格只应出现在句首 '*' 标记后面。
    实测正文里有 8 处半角空格（第 6／7／10／20／21 课），它们把两个词粘成一段，
    分词器认不出词界（「この ノートと」会变成一个词块）。句首标记保持原样。
    """
    m = _LEAD_MARK.match(raw or '')
    head = m.group(0) if m else ''
    body = (raw or '')[len(head):]
    return head + body.replace(' ', '　')


def patch_raw(raw):
    """套用 SOURCE_PATCHES（并统一词间分隔）。返回 (修订后的 raw, 是否修订过)。"""
    out = raw
    for bad, good in SOURCE_PATCHES:
        out = out.replace(bad, good)
    out = _fix_half_width_spaces(out)
    return out, out != raw


def clean_romaji(s):
    """去掉罗马音里不属于读音的东西：漏注音的汉字（汉语原文）、汉语引号。"""
    s = _CJK.sub('', s)
    s = _CN_QUOTE.sub('', s)
    s = re.sub(r'\(\s*\)', '', s)
    s = re.sub(r'\s+', ' ', s)
    return s.strip()




def word_romaji(word_clean, kana):
    if not kana:
        return ''
    if word_clean in WORD_WA:
        return WORD_WA[word_clean]
    return A.kana_to_romaji(kana)


def title_romaji(title_clean, title_ruby):
    """课本标题没有 jp_raw，只有 <ruby> 振假名文本，先还原成「漢字(かな)」再分析。"""
    annotated = _RUBY.sub(lambda m: '%s(%s)' % (m.group(1), m.group(2)), title_ruby or title_clean)
    return clean_romaji(M.analyze_sentence(annotated)['romaji'])


def iter_sentences(lesson):
    """一课里所有带 jp_raw 的句子（基本课文／会话／应用课文），带出处标签。"""
    for s in lesson.get('basic4') or []:
        yield 'basic4', s
    for s in lesson.get('basicc') or []:
        yield 'basicc', s
    for sec in lesson.get('context_sections') or []:
        for s in sec:
            if s.get('type') == 'dialogue':
                yield 'context', s


def build(lessons):
    sentences = {}
    words = {}
    titles = {}
    for les in lessons:
        t = les.get('title_clean') or ''
        if t:
            titles[t] = title_romaji(t, les.get('title_ruby'))
        for w in les.get('words') or []:
            wc = (w.get('word_clean') or '').strip()
            if wc and wc not in words:
                words[wc] = word_romaji(wc, w.get('kana') or '')
        for kind, s in iter_sentences(les):
            raw = s.get('jp_raw') or ''
            if raw and raw not in sentences:
                sentences[raw] = sentence_entry(raw)
    return {
        'meta': {
            'generated_by': 'build_romaji.py',
            'source': 'data/lessons.json 的 jp_raw 假名注音',
            'note': 'lessons.json 的 romaji / title_romaji 是 pykakasi 产物，已废弃不用',
            'patched': [list(p) for p in SOURCE_PATCHES],
            'counts': {'sentences': len(sentences), 'words': len(words), 'titles': len(titles)},
        },
        'sentences': sentences,
        'words': words,
        'titles': titles,
    }


def self_check(data, lessons):
    """结构与读音不变量。返回问题列表（空 = 通过）。"""
    problems = []
    bad_script = re.compile(r'[\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff]')
    for raw, ent in data['sentences'].items():
        rj = ent.get('romaji') or ''
        if not rj:
            problems.append('句子罗马音为空：%s' % raw)
            continue
        m = bad_script.search(rj)
        if m:
            problems.append('罗马音残留假名/汉字「%s」：%s → %s' % (m.group(0), raw, rj))
        # 助词读音：は＝wa、へ＝e、を＝o。ha/he/wo 作为独立词一定是误读
        for tok, why in (('ha', 'は 被读成 ha'), ('he', 'へ 被读成 he'),
                         ('wo', 'を 被读成 wo'), ('deha', 'では 被读成 deha')):
            if re.search(r'(^|\s)%s($|[\s.,!?])' % tok, rj):
                problems.append('%s：%s → %s' % (why, raw, rj))
        if '  ' in rj:
            problems.append('罗马音出现连续空格：%s → %s' % (raw, rj))
    for wc, rj in data['words'].items():
        if not rj:
            problems.append('词表罗马音为空：%s' % wc)
        elif bad_script.search(rj):
            problems.append('词表罗马音残留假名/汉字：%s → %s' % (wc, rj))
    for tc, rj in data['titles'].items():
        if not rj:
            problems.append('标题罗马音为空：%s' % tc)
        elif bad_script.search(rj):
            problems.append('标题罗马音残留假名/汉字：%s → %s' % (tc, rj))
    # 与透视图的整句罗马音保持一致（第1～4课两边都有，必须同源同结果）
    if os.path.exists(EXEMPLARS_PATH):
        with io.open(EXEMPLARS_PATH, encoding='utf-8') as f:
            exs = json.load(f)
        for e in exs:
            if not e.get('auto_generated'):
                continue
            sid = e.get('source_id')
            raw = None
            for les in lessons:
                for s in (les.get('basic4') or []):
                    if s.get('id') == sid:
                        raw = s.get('jp_raw')
            if raw and raw in data['sentences']:
                mine = data['sentences'][raw]['romaji']
                if mine != (e.get('sentence_romaji') or ''):
                    problems.append('%s 透视图整句罗马音与数据层不一致：%s ≠ %s'
                                    % (e['id'], e.get('sentence_romaji'), mine))
    return problems


def main():
    check_only = '--check' in sys.argv
    with io.open(LESSONS_PATH, encoding='utf-8') as f:
        lessons = json.load(f)
    data = build(lessons)

    if check_only:
        with io.open(OUT_PATH, encoding='utf-8') as f:
            on_disk = json.load(f)
        if on_disk.get('sentences') != data['sentences']:
            print('!! data/romaji.json 与 lessons.json 不同步，请重新运行 build_romaji.py')
            raise SystemExit(1)
        if on_disk.get('words') != data['words'] or on_disk.get('titles') != data['titles']:
            print('!! data/romaji.json 的词表/标题部分不同步，请重新运行 build_romaji.py')
            raise SystemExit(1)

    problems = self_check(data, lessons)
    print('罗马音数据层：句子 %d、词表 %d、标题 %d'
          % (len(data['sentences']), len(data['words']), len(data['titles'])))
    if problems:
        print('!! 自检发现 %d 个问题：' % len(problems))
        for p in problems[:40]:
            print('   -', p)
        raise SystemExit(1)
    print('   自检：通过（无残留假名/汉字、无助词读音误读、与透视图同源）')

    if not check_only:
        with io.open(OUT_PATH, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=1)
        print('已生成 %s' % OUT_PATH)


if __name__ == '__main__':
    main()
