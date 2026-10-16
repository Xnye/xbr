# -*- coding: utf-8 -*-
"""
annot.py — 课文注音标注工具

内容层统一使用「漢字(かな)」内联标注语法书写例句，例如：
    李(り)さんは　中国人(ちゅうごくじん)です。

本模块负责把该标注展开为三种形态：
  1. clean  : 李さんは　中国人です。          （纯文本，喂给 TTS）
  2. ruby   : <ruby>李<rt>り</rt></ruby>さんは…  （前端振假名渲染）
  3. romaji : ri-san wa  chuugokujin desu.    （赫本式罗马音，从假名直转）

注意：罗马音一律从「假名注音」推导，不从汉字推导。
现有 lessons.json 的 romaji 由 pykakasi 对整句汉字转换而来，存在误读
（如第1课「李(り)さん」被转成 sumomo san），本模块不复用该字段。
"""

import re

# ---------------------------------------------------------------- 假名 → 罗马音
_KANA = {
    'あ': 'a', 'い': 'i', 'う': 'u', 'え': 'e', 'お': 'o',
    'か': 'ka', 'き': 'ki', 'く': 'ku', 'け': 'ke', 'こ': 'ko',
    'さ': 'sa', 'し': 'shi', 'す': 'su', 'せ': 'se', 'そ': 'so',
    'た': 'ta', 'ち': 'chi', 'つ': 'tsu', 'て': 'te', 'と': 'to',
    'な': 'na', 'に': 'ni', 'ぬ': 'nu', 'ね': 'ne', 'の': 'no',
    'は': 'ha', 'ひ': 'hi', 'ふ': 'fu', 'へ': 'he', 'ほ': 'ho',
    'ま': 'ma', 'み': 'mi', 'む': 'mu', 'め': 'me', 'も': 'mo',
    'や': 'ya', 'ゆ': 'yu', 'よ': 'yo',
    'ら': 'ra', 'り': 'ri', 'る': 'ru', 'れ': 're', 'ろ': 'ro',
    'わ': 'wa', 'ゐ': 'i', 'ゑ': 'e', 'を': 'o', 'ん': 'n',
    'が': 'ga', 'ぎ': 'gi', 'ぐ': 'gu', 'げ': 'ge', 'ご': 'go',
    'ざ': 'za', 'じ': 'ji', 'ず': 'zu', 'ぜ': 'ze', 'ぞ': 'zo',
    'だ': 'da', 'ぢ': 'ji', 'づ': 'zu', 'で': 'de', 'ど': 'do',
    'ば': 'ba', 'び': 'bi', 'ぶ': 'bu', 'べ': 'be', 'ぼ': 'bo',
    'ぱ': 'pa', 'ぴ': 'pi', 'ぷ': 'pu', 'ぺ': 'pe', 'ぽ': 'po',
    'ぁ': 'a', 'ぃ': 'i', 'ぅ': 'u', 'ぇ': 'e', 'ぉ': 'o',
    'ゃ': 'ya', 'ゅ': 'yu', 'ょ': 'yo', 'っ': 'QQ', 'ー': 'HH',
    'ア': 'a', 'イ': 'i', 'ウ': 'u', 'エ': 'e', 'オ': 'o',
    'カ': 'ka', 'キ': 'ki', 'ク': 'ku', 'ケ': 'ke', 'コ': 'ko',
    'サ': 'sa', 'シ': 'shi', 'ス': 'su', 'セ': 'se', 'ソ': 'so',
    'タ': 'ta', 'チ': 'chi', 'ツ': 'tsu', 'テ': 'te', 'ト': 'to',
    'ナ': 'na', 'ニ': 'ni', 'ヌ': 'nu', 'ネ': 'ne', 'ノ': 'no',
    'ハ': 'ha', 'ヒ': 'hi', 'フ': 'fu', 'ヘ': 'he', 'ホ': 'ho',
    'マ': 'ma', 'ミ': 'mi', 'ム': 'mu', 'メ': 'me', 'モ': 'mo',
    'ヤ': 'ya', 'ユ': 'yu', 'ヨ': 'yo',
    'ラ': 'ra', 'リ': 'ri', 'ル': 'ru', 'レ': 're', 'ロ': 'ro',
    'ワ': 'wa', 'ヰ': 'i', 'ヱ': 'e', 'ヲ': 'o', 'ン': 'n',
    'ガ': 'ga', 'ギ': 'gi', 'グ': 'gu', 'ゲ': 'ge', 'ゴ': 'go',
    'ザ': 'za', 'ジ': 'ji', 'ズ': 'zu', 'ゼ': 'ze', 'ゾ': 'zo',
    'ダ': 'da', 'ヂ': 'ji', 'ヅ': 'zu', 'デ': 'de', 'ド': 'do',
    'バ': 'ba', 'ビ': 'bi', 'ブ': 'bu', 'ベ': 'be', 'ボ': 'bo',
    'パ': 'pa', 'ピ': 'pi', 'プ': 'pu', 'ペ': 'pe', 'ポ': 'po',
    'ァ': 'a', 'ィ': 'i', 'ゥ': 'u', 'ェ': 'e', 'ォ': 'o',
    'ャ': 'ya', 'ュ': 'yu', 'ョ': 'yo', 'ッ': 'QQ', 'ヴ': 'bu',
    '・': '', '　': '  ', ' ': ' ',
}

# 全角英数記号（Ａ-Ｚ ０-９ ！？（）…）→ 半角。
# 教材里出现「Ｔシャツ」这类写法，罗马音行不该混着全角字母。
_FW_ASCII = {chr(0xFF01 + i): chr(0x21 + i) for i in range(94)}

_YOON = {
    # 拗音词干表。注意：这里给的是「小写や行假名之前的辅音部分」，
    # きゃ＝ky+a、しゃ＝sh+a。き／に／ひ／み／り／ぎ／び／ぴ 必须带上 y，
    # 否则 きょう 会转成 kou（应为 kyou）、りょこう 会转成 rokou（应为 ryokou）。
    'き': 'ky', 'し': 'sh', 'ち': 'ch', 'に': 'ny', 'ひ': 'hy', 'み': 'my',
    'り': 'ry', 'ぎ': 'gy', 'じ': 'j', 'び': 'by', 'ぴ': 'py', 'ぢ': 'j',
    'キ': 'ky', 'シ': 'sh', 'チ': 'ch', 'ニ': 'ny', 'ヒ': 'hy', 'ミ': 'my',
    'リ': 'ry', 'ギ': 'gy', 'ジ': 'j', 'ビ': 'by', 'ピ': 'py', 'ヂ': 'j',
}
_SMALL_Y = set('ゃゅょャュョ')

# 外来语特殊拗音（必须先于通用拗音规则匹配）
_SPECIAL_COMBO = {
    'ジェ': 'je', 'シェ': 'she', 'チェ': 'che', 'ティ': 'ti', 'ディ': 'di',
    'デュ': 'dyu', 'デャ': 'dya', 'ファ': 'fa', 'フィ': 'fi', 'フェ': 'fe',
    'ウィ': 'wi', 'ウェ': 'we', 'ウォ': 'wo', 'ヴォ': 'vo', 'ツァ': 'tsa',
    'ツィ': 'tsi', 'イェ': 'ye', 'フュ': 'fyu', 'ミュ': 'myu', 'ギュ': 'gyu',
    'ヒュ': 'hyu', 'ビュ': 'byu', 'ピュ': 'pyu', 'リュ': 'ryu', 'ニュ': 'nyu',
    'キュ': 'kyu', 'シュ': 'shu', 'チュ': 'chu', 'ジュ': 'ju', 'ブュ': 'byu',
}

# 助词特殊读法（は→wa, へ→e, を→o）由调用方在分词阶段标记，此处按普通假名转。
_PARTICLE_OVERRIDE = {'は': 'wa', 'へ': 'e', 'を': 'o'}


def kana_to_romaji(kana, particle_positions=None):
    """
    把假名串转为赫本式罗马音。
    particle_positions: set of int，指明哪些下标处的「は/へ/を」应按助词读音转写。
    """
    out = []
    i = 0
    n = len(kana)
    while i < n:
        ch = kana[i]

        # 外来语特殊拗音
        if i + 1 < n:
            combo = kana[i:i + 2]
            if combo in _SPECIAL_COMBO:
                out.append(_SPECIAL_COMBO[combo])
                i += 2
                continue

        # 拗音：き＋ゃ → kya
        if i + 1 < n and kana[i + 1] in _SMALL_Y and ch in _YOON:
            stem = _YOON[ch]
            tail = {'ゃ': 'a', 'ゅ': 'u', 'ょ': 'o', 'ャ': 'a', 'ュ': 'u', 'ョ': 'o'}[kana[i + 1]]
            out.append(stem + tail)
            i += 2
            continue

        if ch in _KANA:
            r = _KANA[ch]
            if ch in _PARTICLE_OVERRIDE and particle_positions and i in particle_positions:
                r = _PARTICLE_OVERRIDE[ch]
            out.append(r)
        elif ch == '～' or ch == '~':
            out.append('~')
        else:
            out.append(_FW_ASCII.get(ch, ch))
        i += 1

    s = ''.join(out)

    # 促音 QQ → 后接辅音双写；长音 HH → 前接元音延长。手工扫描比正则清晰。
    res = []
    j = 0
    while j < len(s):
        if s.startswith('QQ', j):
            # 找到后继辅音，把促音换成那个辅音（ッシ→sshi，ッチ→tchi，ッパ→ppa）
            k = j + 2
            while k < len(s) and s[k] == ' ':
                k += 1
            nxt = s[k:k + 2]
            if nxt == 'sh':
                # いっしょ → issho（不是 itsho）：ッシ 的促音是 s
                res.append('s')
            elif nxt == 'ch':
                # マッチ → matchi：ッチ 的促音是 t
                res.append('t')
            elif nxt == 'ts':
                res.append('t')
            elif k < len(s) and s[k] == 'h':
                # 促音＋ハ行 → 促音便＋連濁：一本 いっほん → ippon、一発 → ippatsu。
                # 教材只注了本(ほん)，但实际读法一定是 ぽん（音读量词的连浊）。
                s = s[:k] + 'p' + s[k + 1:]
                res.append('p')
            elif k < len(s) and s[k].isalpha():
                res.append(s[k])
            else:
                res.append('t')
            j += 2
            continue
        if s.startswith('HH', j):
            # 长音：按前一个元音延长
            prev_vowel = ''
            for c in reversed(res):
                if c in 'aiueo':
                    prev_vowel = c
                    break
            res.append(prev_vowel or '-')
            j += 2
            continue
        res.append(s[j])
        j += 1
    s = ''.join(res)

    # 收尾清洗
    s = re.sub(r'\s+', ' ', s).strip()
    return s


# ---------------------------------------------------------------- 注音展开
_ANNOT = re.compile(r'([^\s　、。！？（）()]+?)\(([ぁ-んァ-ンー]+)\)')


def expand(annotated):
    """
    把「漢字(かな)」标注展开。
    返回 dict(clean=..., ruby=..., reading=..., particle_idx=...)
      reading      : 全假名读法（汉字替换为其注音），用于生成罗马音
      particle_idx : reading 中应读作助词音（は→wa / へ→e / を→o）的下标集合

    助词判定：新标日课文以全角空格「　」切分语块，助词总贴在语块末尾，
    因此「字面书写的是/へ/を + 紧跟全角空格或句读」即判定为助词。
    汉字注音内部的 は/へ/を 一律按本音处理（如 母(はは) → haha）。
    """
    clean_parts = []
    ruby_parts = []
    read_parts = []
    particle_idx = set()
    reading_len = 0

    pos = 0
    for m in _ANNOT.finditer(annotated):
        pre = annotated[pos:m.start()]
        # 字面片段：逐字扫描，判定助词
        for off, ch in enumerate(pre):
            src_i = pos + off
            nxt = annotated[src_i + 1] if src_i + 1 < len(annotated) else ''
            if ch in 'はへを' and (nxt in '　。，、！？…' or nxt == ''):
                particle_idx.add(reading_len)
            read_parts.append(ch)
            reading_len += 1
        clean_parts.append(pre)
        ruby_parts.append(pre)

        base, kana = m.group(1), m.group(2)
        clean_parts.append(base)
        ruby_parts.append('<ruby>%s<rt>%s</rt></ruby>' % (base, kana))
        read_parts.append(kana)
        reading_len += len(kana)
        pos = m.end()

    tail = annotated[pos:]
    for off, ch in enumerate(tail):
        src_i = pos + off
        nxt = annotated[src_i + 1] if src_i + 1 < len(annotated) else ''
        if ch in 'はへを' and (nxt in '　。，、！？…' or nxt == ''):
            particle_idx.add(reading_len)
        read_parts.append(ch)
        reading_len += 1
    clean_parts.append(tail)
    ruby_parts.append(tail)

    return {
        'clean': ''.join(clean_parts),
        'ruby': ''.join(ruby_parts),
        'reading': ''.join(read_parts),
        'particle_idx': particle_idx,
    }


def sentence(annotated, romaji=None):
    """便捷封装：返回 annot / clean / ruby / reading / romaji 五件套。"""
    e = expand(annotated)
    e['annot'] = annotated
    e['romaji'] = romaji if romaji else kana_to_romaji(e['reading'], e['particle_idx'])
    return e


if __name__ == '__main__':
    tests = [
        '李(り)さんは　中国人(ちゅうごくじん)です。',
        '森(もり)さんは　学生(がくせい)では　ありません。',
        'ここは　デパートです。',
        '部屋(へや)に　机(つくえ)と　いすが　あります。',
        'この　カメラは　スミスさんのです。',
        '七時(しちじ)に　起(お)きます。',
        '横浜(よこはま)に　あります。',
    ]
    for t in tests:
        s = sentence(t)
        print(s['clean'])
        print('  ruby  :', s['ruby'])
        print('  romaji:', s['romaji'])
