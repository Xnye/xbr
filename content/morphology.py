# -*- coding: utf-8 -*-
"""
morphology.py — 新标日课文分词与助词知识库

解构引擎与罗马音生成都依赖本模块。核心前提来自新标日课文的排版规律：

  * 语块之间用全角空格「　」分隔，助词几乎总贴在语块末尾
    例：「李さんは　中国人です。」→ [李さんは] [中国人です]
  * jp_raw 用「!」标记词首、用「(かな)」标记汉字注音，是权威读音来源
    例：'* !李(り)さんは\u3000!中国人(ちゅうごくじん)です。'

因此分词策略是：先按「　」和句读切段，再从段尾剥离助词，
最后把段体查词表得到词义。不做通用形态素解析，只吃这套教材的规整排版。
"""

import json
import os
import re

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'data')

# ============================================================ 1. 助词知识库
# color 必须与 css/main.css 中的 --color-particle-* 令牌同名
PARTICLES = {
    'は': {
        'color': 'blue', 'name': '提示助词（主题）',
        'gloss': '话题标记',
        'desc': '【は】读作 wa。它不是「是」，而是一盏聚光灯：先把某个东西推到台前——「关于这个嘛……」，后面才是你要说的话。它圈定的是谈话领域，不是动作执行者。',
    },
    'が': {
        'color': 'red', 'name': '主格助词（主语）',
        'gloss': '主语标记',
        'desc': '【が】才是真正的主格标记，指向动作或状态的当事者。新信息、疑问词做主语、存在句的主体，都必须用が而不能用は。',
    },
    'を': {
        'color': 'orange', 'name': '宾格助词（对象）',
        'gloss': '宾语标记',
        'desc': '【を】读作 o。标记及物动词的作用对象，也可标记移动动词经过的场所（公園を散歩する）。',
    },
    'に': {
        'color': 'purple', 'name': '格助词（归着点）',
        'gloss': '在／到（点）',
        'desc': '【に】的核心意象是「箭靶上的红心」——动作或存在的归着点。存在场所（机があります）、时间点（七時に）、移动终点（日本に行きます）、间接对象（李さんにあげる）都由它标记。',
    },
    'で': {
        'color': 'indigo', 'name': '格助词（活动场所／手段）',
        'gloss': '在（动作）／用',
        'desc': '【で】标记「事情展开的舞台」或「所用的手段材料」。与に的关键区别：に是静态归着点，で是动态活动范围。食堂で食べる（在食堂吃·动作）と食堂にある（在食堂·存在），两个「在」日语分得很清楚。',
    },
    'へ': {
        'color': 'magenta', 'name': '格助词（方向）',
        'gloss': '朝／向',
        'desc': '【へ】读作 e。标记移动的方向而非终点，强调「朝那个方向去」的过程感。与に相比，へ更看重方向性，に更看重抵达点。',
    },
    'と': {
        'color': 'yellow', 'name': '并列／伴随助词',
        'gloss': '和／跟',
        'desc': '【と】把两个名词平等地绑在一起（AとB），或标记共同行为的伙伴（森さんと行きました）。它是完全并列，不像や那样暗示「还有别的没列出来」。',
    },
    'の': {
        'color': 'teal', 'name': '连体助词（所属／属性）',
        'gloss': '的',
        'desc': '【の】是唯一能把「名词＋名词」焊接成一个名词短语的胶水，让前一个名词降级为后一个名词的修饰语。日语修饰语永远在被修饰语之前，所以「ＪＣ企画の社員」与中文「JC策划的职员」语序一致。',
    },
    'も': {
        'color': 'pink', 'name': '提示助词（类同）',
        'gloss': '也',
        'desc': '【も】是は的替身：它同样提示主题，但附带一句「和前面那个一样」。所以は和も不能同时出现（×私も行きますは），も直接顶替は的位置。',
    },
    'から': {
        'color': 'cyan', 'name': '格助词／接续助词（起点・原因）',
        'gloss': '从／因为',
        'desc': '【から】的本义是「起点」——时间起点、空间起点，引申为逻辑起点即「原因」。接名词时是格助词（九時から），接简体谓语时是接续助词（雨だから）。',
    },
    'まで': {
        'color': 'brown', 'name': '格助词（终点）',
        'gloss': '到／直到',
        'desc': '【まで】标记行程或时间的终点，与から成对使用：から是起跑线，まで是终点线。',
    },
    # な 只作为「块内连接框」出现（连体形），不进 PEELABLE——罗马音层不管它，
    # 所以 きれいな人形 仍然是 kireina ningyou（教材读法），
    # 而透视图里 静かな町 会显示成「静か［な］町」一个成分。
    'な': {
        'color': 'teal', 'name': '连体助词（な形容词）',
        'gloss': '的',
        'desc': '【な】是な形容词的连体形标志：静かな町＝安静的城市。它和 の 干的是同一件事'
                '——把前面的词降级成修饰语——但分工不同：の 连的是名词（京都の紅葉），'
                'な 连的是な形容词（静かな町）。而且 な 只出现在名词前面：'
                '句尾直接接 です（静かです），不能说 静かなです。',
    },
    'より': {
        'color': 'cyan', 'name': '格助词（比较基准）',
        'gloss': '比',
        'desc': '【より】本义是「起点」，与から同源；比较时它划出起跑线：「Bより」＝以B为基准。'
                '李さんは森さんより若いです——视线从森先生出发落到小李身上。'
                '它只标基准，不标谁高谁低，高下由后面的形容词说出来。',
    },
    'ほど': {
        'color': 'cyan', 'name': '副助词（程度基准）',
        'gloss': '到……的程度',
        'desc': '【ほど】划出「照这个基准衡量」的程度线，几乎总和否定连用：'
                '神戸は大阪ほどにぎやかではありません＝神户热闹的程度够不上大阪。'
                '与より的分工：より说「比谁更……」，ほど说「没到那个程度」。',
    },
    'か': {
        'color': 'slate', 'name': '疑问终助词',
        'gloss': '吗／呢',
        'desc': '【か】把整个句子装进一个「问号盒子」，放在句尾全句变疑问。日语语序不会因为疑问而改变——不需要像英语那样倒装。',
    },
    'ね': {
        'color': 'slate', 'name': '终助词（确认・共感）',
        'gloss': '……吧／呢',
        'desc': '【ね】放在句尾，把话说了一半递给对方：「我是这么看的，你也这么觉得吧？」它征求认同、软化断言，是日语维系人际同步感的高频装置。',
    },
    'よ': {
        'color': 'slate', 'name': '终助词（告知）',
        'gloss': '……哦／啊',
        'desc': '【よ】把信息推给对方：「我告诉你一件你不知道的事」。与ね的方向相反——ね是求共鸣，よ是单向告知。',
    },
    'では': {
        'color': 'green', 'name': '断定助动词的连用形＋は',
        'gloss': '（否定前置）',
        'desc': '【では】＝で（场所・状态格）＋は（提示）。它是名词谓语句否定的固定入口：です的否定不说「×ですない」，而是把名词谓语拆成「で＋ある」，再否定存在动词 → ではありません。口语缩约成 じゃ。',
    },
    'じゃ': {
        'color': 'green', 'name': 'では的口语缩约',
        'gloss': '（否定前置·口语）',
        'desc': '【じゃ】＝では的口语缩约形。意思完全相同，但じゃ偏口语、では偏正式。考试作文和商务场合写では，日常会话用じゃ。',
    },
    'ですか': {
        'color': 'green', 'name': '断定＋疑问',
        'gloss': '是……吗',
        'desc': '【ですか】＝です（断定）＋か（疑问）。语序与陈述句完全一致，只在句尾加一个か。',
    },
    'です': {
        'color': 'green', 'name': '断定助动词（礼貌体）',
        'gloss': '是（断定）',
        'desc': '【です】本身没有「是」的实义，它是句尾落下的一枚礼貌印章：「我这样断定，并且对你保持礼貌」。真正的判断内容由前面的名词承担。',
    },
    'ではありません': {
        'color': 'green', 'name': '断定・否定（礼貌体）',
        'gloss': '不是',
        'desc': '【ではありません】字面＝「在……的立场上，（事实）不存在」。で切换名词舞台，ある表存在，ません否定它。这是名词谓语句的标准否定形。',
    },
    'があります': {
        'color': 'green', 'name': '存在动词（无意志物）',
        'gloss': '有／在',
        'desc': '【あります】表示无意志之物的存在：桌椅、建筑、抽象事物、植物。它的存在是「被摆放着」的静态存在。',
    },
    'がいます': {
        'color': 'green', 'name': '存在动词（有意志者）',
        'gloss': '有／在',
        'desc': '【います】表示有意志者的存在：人、动物。日语把「会自己动的东西」和「不会动的东西」分成两套存在动词，这是中文没有的分野。',
    },
    'や': {
        'color': 'yellow', 'name': '并列助词（部分列举）',
        'gloss': '和…等',
        'desc': '【や】把几个名词并列起来，但暗示「还有别的没说出来」：机やいす（桌子、椅子等等）。と 是完整列举「只有这些」，や 是举例「有这些，也有别的」。',
    },
}

# 同一个 か，位置不同、职责不同：
#   句尾的 か 是疑问终助词（走 final，见 PARTICLES['か']）
#   名词后面的 か 是并列／不定助词（パンか お粥、だれか います）
PARTICLES_NONFINAL = {
    'か': {
        'color': 'slate', 'name': '并列・不定助词',
        'gloss': '或／某',
        'desc': '【か】夹在名词后面有两个用法：①并列选择（パンか お粥を 食べます 面包或粥）；②不定（だれか います 有人）。共同点是「不指定是哪一个」——这正是 か 的本义「不确定」。',
    },
}

# 多字助词优先匹配（从长到短）
_PARTICLE_ORDER = sorted(PARTICLES.keys(), key=len, reverse=True)

# 句读与分隔符
_SEPARATORS = set('　。，、！？…・')
_PUNCT_MAP = {'。': '.', '、': ',', '！': '!', '？': '?', '，': ',', '…': '...'}


# ============================================================ 2. 词表
SUPPLEMENT = {
    # 称谓
    'さん': ('さん', '名接', '先生／女士（敬称）', 'Mr./Ms.'),
    'くん': ('くん', '名接', '君（对晚辈男性）', '(suffix for boys)'),
    'ちゃん': ('ちゃん', '名接', '（对小孩的亲昵称呼）', '(child suffix)'),
    '様': ('さま', '名', '先生／女士（更恭敬）', 'Mr./Ms. (honorific)'),
    # 第1课
    '李秀麗': ('りしゅうれい', '专', '李秀丽', 'Li Xiuli'),
    '小野緑': ('おのみどり', '专', '小野绿', 'Ono Midori'),
    'JC企画': ('ジェーシーきかく', '专', 'JC策划公司', 'JC Planning Co.'),
    'ＪＣ企画': ('ジェーシーきかく', '专', 'JC策划公司', 'JC Planning Co.'),
    'はじめまして': ('はじめまして', '熟语', '初次见面', 'Nice to meet you'),
    # 第2课
    '５２歳': ('ごじゅうにさい', '名', '52岁', '52 years old'),
    'スミス': ('スミス', '专', '史密斯', 'Smith'),
    # 第3课
    '七階': ('ななかい', '名', '七层', '7th floor'),
    '一階': ('いっかい', '名', '一层', '1st floor'),
    '二階': ('にかい', '名', '二层', '2nd floor'),
    '三階': ('さんがい', '名', '三层', '3rd floor'),
    'かばん売り場': ('かばんうりば', '名', '卖包的柜台', 'bag counter'),
    '五千八百円': ('ごせんはっぴゃくえん', '名', '5800日元', '5,800 yen'),
    '五百円': ('ごひゃくえん', '名', '500日元', '500 yen'),
    '売り場': ('うりば', '名', '柜台／出售处', 'sales counter'),
    # 第4课
    '庭': ('にわ', '名', '院子', 'garden'),
    '上に': ('うえに', '名+助', '在……上面', 'on top of'),
    '誰も': ('だれも', '代', '谁（都）／任何人', 'anyone / nobody'),
    '横浜': ('よこはま', '专', '横滨', 'Yokohama'),
    '名古屋': ('なごや', '专', '名古屋', 'Nagoya'),
    '大阪': ('おおさか', '专', '大阪', 'Osaka'),
    'JR': ('ジェーアール', '专', 'JR（日本铁路）', 'JR'),
    'ＪＲ': ('ジェーアール', '专', 'JR（日本铁路）', 'JR'),
    # 通用副词・接续
    'ええと': ('ええと', '叹', '嗯……（思考中）', 'well...'),
    'あのう': ('あのう', '叹', '请问／那个……', 'excuse me'),
    'はい': ('はい', '叹', '是／好', 'yes'),
    'いいえ': ('いいえ', '叹', '不／不是', 'no'),
    'ここ': ('ここ', '代', '这里', 'here'),
    'そこ': ('そこ', '代', '那里（近听话人）', 'there (near you)'),
    'あそこ': ('あそこ', '代', '那里（远双方）', 'over there'),
    'こちら': ('こちら', '代', '这边（礼貌）', 'this way (polite)'),
    'そちら': ('そちら', '代', '那边（礼貌）', 'that way (polite)'),
    'あちら': ('あちら', '代', '那边（礼貌·远）', 'that way over there'),
    'どこ': ('どこ', '疑', '哪里', 'where'),
    'どちら': ('どちら', '疑', '哪边／哪里（礼貌）', 'which way'),
    'これ': ('これ', '代', '这个', 'this'),
    'それ': ('それ', '代', '那个（近听话人）', 'that'),
    'あれ': ('あれ', '代', '那个（远双方）', 'that over there'),
    'どれ': ('どれ', '疑', '哪个', 'which one'),
    'この': ('この', '连体', '这个', 'this'),
    'その': ('その', '连体', '那个', 'that'),
    'あの': ('あの', '连体', '那个（远）', 'that over there'),
    'どの': ('どの', '连体', '哪个', 'which'),
    '何': ('なん', '疑', '什么', 'what'),
    'だれ': ('だれ', '疑', '谁', 'who'),
    'どなた': ('どなた', '疑', '哪位（礼貌）', 'who (polite)'),
    'いくら': ('いくら', '名', '多少钱', 'how much'),
    'わたし': ('わたし', '代', '我', 'I'),
    '私': ('わたし', '代', '我', 'I'),
    # ---- 第5课起：教材词表没收录的词（数字＋时/量词这类组合）----
    '四時': ('よじ', '名', '4点', 'four o\'clock'),
    '七時': ('しちじ', '名', '7点', 'seven o\'clock'),
    '六時': ('ろくじ', '名', '6点', 'six o\'clock'),
    '八時': ('はちじ', '名', '8点', 'eight o\'clock'),
    '九時': ('くじ', '名', '9点', 'nine o\'clock'),
    '十時': ('じゅうじ', '名', '10点', 'ten o\'clock'),
    '五時': ('ごじ', '名', '5点', 'five o\'clock'),
    '十一時': ('じゅういちじ', '名', '11点', 'eleven o\'clock'),
    '十二時': ('じゅうにじ', '名', '12点', 'twelve o\'clock'),
    '勉強': ('べんきょう', '名', '学习', 'study'),
    # ---- 第9课起：形容词与比较表达 ----
    # 教材词表按「〜い／〜な」收录形容词。第9课课文用的是 熱い（あつい，物体热），
    # 同音的 暑い（天气热）词表里有，熱い 没有，靠这一条补上；
    # ほう（方）是第12课比较句的核心名词：「Aのほうが」＝A这一边。
    '熱い': ('あつい', '形1', '（物体）热，烫', 'hot'),
    'ほう': ('ほう', '名', '（比较的）一方', 'side (in a comparison)'),
}


def build_lexicon():
    """合并 lessons.json 全48课词表 + 补充词条。返回 {词面: {...}}。"""
    lex = {}
    path = os.path.join(DATA_DIR, 'lessons.json')
    if os.path.exists(path):
        with open(path, encoding='utf-8') as f:
            lessons = json.load(f)
        for les in lessons:
            for w in les.get('words') or []:
                surface = w.get('word_clean', '').strip()
                if not surface:
                    continue
                if surface not in lex:
                    lex[surface] = {
                        'kana': w.get('kana', ''),
                        'pos': w.get('pos', ''),
                        'zh': w.get('desc', ''),
                    }
    for k, v in SUPPLEMENT.items():
        lex[k] = {'kana': v[0], 'pos': v[1], 'zh': v[2], 'en': v[3] if len(v) > 3 else ''}
    return lex


LEXICON = build_lexicon()


def lookup(surface):
    """查词表。支持整词命中与前缀最长命中。"""
    surface = surface.strip()
    if not surface:
        return None
    if surface in LEXICON:
        return dict(LEXICON[surface], surface=surface)
    # 前缀最长匹配（处理「かばん売り場」这类复合词的部分命中）
    for n in range(len(surface), 1, -1):
        head = surface[:n]
        if head in LEXICON:
            return dict(LEXICON[head], surface=head, partial=surface[n:])
    return None


# ============================================================ 3. 注音展开
_ANNOT_FULL = re.compile(r'^([^\s　、。！？（）()\x01]+?)\(([ぁ-んァ-ンー]+)\)$')
_ANNOT_INLINE = re.compile(r'([^\s　、。！？()]+?)\(([ぁ-んァ-ンー]+)\)')


# 教材注音里的全角空格占位：当注音汉字串内部还夹着送假名时，
# 排版把送假名写成全角空格占位，例如
#     売り出(う　だ)  → 売(う) り 出(だ)      （うりだ）
#     引っ越(ひ　こ)  → 引(ひ) っ 越(こ)      （ひっこ）
#     出か(で　)け    → 出(で) か             （でか）
# 占位符与 surface 里的假名字符一一对齐，展开时按序分配即可。
# 不展开的话，这些句子整段注解会被当作普通文本，
# 罗马音里会冒出「引越越(hi ko)shi」这种垃圾。
_ANNOT_PLACEHOLDER = re.compile(
    r'([^\s　、。！？()\x01!]+)\(([ぁ-んァ-ンー　]*　[ぁ-んァ-ンー　]*)\)')


def expand_placeholder_readings(raw):
    """把「漢字串(か　な)」的占位读音展开成连续读音；无占位符的原样返回。"""
    def repl(m):
        surf, kana = m.group(1), m.group(2)
        parts = kana.split('　')
        out = []
        pi = 0
        for ch in surf:
            if _is_hira(ch) or _is_kata(ch):
                out.append(ch)                  # surface 里的送假名，读音就是它自己
            else:
                out.append(parts[pi] if pi < len(parts) else '')
                pi += 1
        return '%s(%s)' % (surf, ''.join(out))

    return _ANNOT_PLACEHOLDER.sub(repl, raw)


def strip_markers(raw):
    """去掉行首的 '* ' 项目符号，把词首标记 ! 统一成控制符 \\x01。"""
    s = raw.strip()
    s = re.sub(r'^[\*＊•]\s*', '', s)
    return s.replace('!', '\x01').strip()


def tokenize_raw(raw):
    """
    把 jp_raw 切成带注音的字面 token 序列，粒度细到「一个注音词」。

    输入：'* !李(り)さんは\u3000!中国人(ちゅうごくじん)です。'
    输出：[
      {'surf':'李','read':'り','ann':True},
      {'surf':'さんは','read':'さんは','ann':False},
      {'surf':'　','sep':True},
      {'surf':'中国人','read':'ちゅうごくじん','ann':True},
      {'surf':'です','read':'です','ann':False},
      {'surf':'。','punct':'.'},
    ]

    ! 视为词首硬边界；「漢字(かな)」单独成 token 并保留 ann=True，
    这样上层能直接拼出 <ruby> 振假名，而不必再猜哪几个字带注音。
    """
    s = expand_placeholder_readings(strip_markers(raw))
    tokens = []
    pending_break = False

    def emit_piece(piece):
        """把 ! 切出的一小块再按注音边界细分。"""
        nonlocal pending_break
        if not piece:
            return
        pos = 0
        for m in _ANNOT_INLINE.finditer(piece):
            if m.start() > pos:
                lit = piece[pos:m.start()]
                tokens.append({'surf': lit, 'read': lit, 'ann': False, 'wb': pending_break})
                pending_break = False
            tokens.append({'surf': m.group(1), 'read': m.group(2), 'ann': True,
                           'wb': pending_break})
            pending_break = False
            pos = m.end()
        if pos < len(piece):
            lit = piece[pos:]
            tokens.append({'surf': lit, 'read': lit, 'ann': False, 'wb': pending_break})
            pending_break = False

    for piece in re.split(r'([\x01　。，、！？…])', s):
        if piece == '':
            continue
        if piece == '\x01':
            pending_break = True
            continue
        if piece in _SEPARATORS:
            pending_break = False
            if piece in _PUNCT_MAP:
                tokens.append({'surf': piece, 'punct': _PUNCT_MAP[piece]})
            else:
                tokens.append({'surf': piece, 'sep': True})
            continue
        emit_piece(piece)
    return tokens

# ============================================================ 4. 谓语与句法分析

# 可剥离的格助词・并列助词・接续助词（谓语另走 _PRED_OR_INFLECT）
# か 在这里只承担「并列・不定」用法（パンか お粥を／だれか います）；
# 句尾疑问的 か 已被终助词那一步先剥走，走不到这里。
# より／ほど 是第12课的比较表达：より 标基准（Bより＝比B），ほど 标程度（Bほど＝到B的程度）。
PEELABLE = ['では', 'じゃ', 'から', 'まで', 'より', 'ほど',
            'は', 'が', 'を', 'に', 'で', 'へ', 'と', 'の', 'も',
            'か', 'や']
_PEEL_ORDER = sorted(PEELABLE, key=len, reverse=True)

# 「ない」前面可以收在这些助词上（ことが ない／では ない／に ない），这时候
# ない 是独立的否定谓词。か／や 不算依据——它们是五段动词ない形的一部分
# （行かない／書かない），拿它们当证据会把 行かない 切成 行＋か＋ない。
_NEG_LEFT_PARTICLES = tuple(p for p in _PEEL_ORDER if p not in ('か', 'や'))

# 词表里的「纯假名词」（word_clean == kana）的读法集合（只取 2 字以上，
# 单字会跟助词撞车）；KANA_READINGS 是所有词条的假名读法（含汉字词的读法）。
# 两者用来判断「剥掉段尾助词之后，剩下的还是不是一个完整的词」：
#     とても  剥 も → とて（不是词）→ 不许剥，罗马音必须写 totemo
#     これは  剥 は → これ（是词）  → 允许剥
KANA_WORDS = {k for k, v in LEXICON.items() if v.get('kana') == k and len(k) >= 2}
_KANA_TAILS = tuple(sorted(KANA_WORDS, key=len, reverse=True))
KANA_READINGS = set(KANA_WORDS)
for _v in LEXICON.values():
    if _v.get('kana') and len(_v['kana']) >= 2:
        KANA_READINGS.add(_v['kana'])
_READING_TAILS = tuple(sorted(KANA_READINGS, key=len, reverse=True))

# 只有 3 字以上的词才可能「跨断点」（断点必在词内部），用它做「词内不切」检查更快
_LONG_TAILS = tuple(w for w in _READING_TAILS if len(w) >= 3)

# 动词按**假名读法**索引（教材词表按汉字词面收录：行きます 的 kana 是 いきます）。
# 课文里出现的是活用形（いって／きいて），要靠读法反查动词，所以单独建一张表：
#   VERB_KANA['いきます'] = '行きます'
VERB_KANA = {}
for _surf, _v in LEXICON.items():
    if '动' in (_v.get('pos') or '') and _v.get('kana'):
        VERB_KANA.setdefault(_v['kana'], _surf)


def _body_is_word(body_surf, body_read, particle=''):
    """
    段尾助词的剥离判定：剥完只剩残干（とて／きっ／ちょっ）就说明那不是助词。
      ① 词体以汉字／片假名收尾 → 助词必然贴在词外：李さんは／猫が／スミスさんの
      ② 词体本身在词表（或人名表）里：これは／だれの／おとといは
      ③ 词体读法是词表里的词（含汉字词的读法），或以某个词收尾：りさん → さん
      ④ 词体＋助词整体是词表里的纯假名词，且助词是 は／へ／を
         （词尾 は 读 wa 本身就是「这里是助词」的证据）：こんにちは → konnichiwa
      ⑤ 词体本身以助词收尾（部屋には／李さんからは）：后面这个助词一定在词外
    """
    if not body_surf:
        return False
    if _has_kanji(body_surf[-1]) or _is_kata(body_surf[-1]):
        return True
    if body_surf in LEXICON or body_surf in NAME_ZH:
        return True
    if particle and body_surf.endswith(tuple(_PEEL_ORDER)):
        # 词体本身以助词收尾（部屋に＋は／李さんから＋は）：后面这个助词一定在词外
        return True
    if particle in ('は', 'へ', 'を') and (body_surf + particle) in KANA_WORDS:
        return True
    if len(body_surf) == 1 and len(particle) > 1:
        # では → で ＋ は：单字残干在多字助词面前是正常词体
        return True
    if not body_read:
        return False
    if body_read in KANA_WORDS:
        return True
    # ⑥ 词体读法是动词的ます形语干（出し|に 行きます／休み|に 行きます）：
    #    动词词表按汉字词面收录（出します），所以要按读法回查一次。
    if VERB_KANA.get(body_read + 'ます'):
        return True
    return any(body_read.endswith(w) for w in _READING_TAILS)




# 存在动词与动词「〜ました」同形：買いました／思いました／使いました 里的
# 「いました」不是存在动词，要用 _existence_ok 先判一下词体。
_EXISTENCE_PREDS = {'あります', 'ありました', 'ありません',
                    'います', 'いました', 'いません'}

def _existence_ok(surf, pred):
    """
    存在动词的词体是否像存在句的主语。判据是「它前面有没有助词」：
      机があります／部屋にあります／学生ではありません／だれかいます → 有助词 → 是
      買いました／思いました／使いました → 汉字词体直接连 いました，中间没有助词
      → 那是动词「〜ました」，不是存在动词。少了这条 kaimashita 会被切成 ka imashita。
      熱くありません（い形容词的否定，第9课）→ 词体收在连用形 く 上，也是「是」；
      判据同样是词表：熱く → 熱い 是词表里的 い形容词。
    """
    head = surf[:-len(pred)]
    if not head:
        return True                      # 整段就是「あります」（应答句）
    if pred in ('ありません', 'ありませんでした') and adj_i_ku_ok(head):
        return True                      # 熱くありません → atsuku arimasen
    return head.endswith(tuple(_PEEL_ORDER)) or head[-1] in '、か'


# 终助词：位于谓语之后，必须最先剥离（一階ですか → か + です）
_FINAL = ['か', 'ね', 'よ']

# 不可剥离词：整体成词，尾部假名与助词同形但绝非助词
NO_PEEL = {'この', 'その', 'あの', 'どの', 'これ', 'それ', 'あれ', 'どれ',
           'ここ', 'そこ', 'あそこ', 'どこ', 'こちら', 'そちら', 'あちら', 'どちら',
           'だれ', '何', 'どなた', 'いくら', 'みんな', 'ほか'}

# 谓语尾：从长到短匹配。值为 (中文词义, 形态说明, 下划线颜色, 直译行短词义)
# 第四个元素专供逐词直译行使用——那一行寸土寸金，必须短。
PREDICATES = {
    'ではありませんでした': ('不是（过去）', '断定・过去・否定', 'green', '不是了'),
    'じゃありませんでした': ('不是（过去·口语）', '断定・过去・否定', 'green', '不是了'),
    'ではありません': ('不是', '断定・否定', 'green', '不是'),
    'じゃありません': ('不是（口语）', '断定・否定', 'green', '不是'),
    'でした': ('是（过去）', '断定・过去', 'green', '曾是'),
    'です': ('是（断定）', '断定助动词', 'green', '是'),
    'ありました': ('有・在（过去）', '存在・无意志・过去', 'green', '曾有'),
    'ありません': ('没有・不存在', '存在・无意志・否定', 'green', '不存在'),
    'あります': ('有・在（物）', '存在动词・无意志', 'green', '有'),
    'いました': ('有・在（过去）', '存在・有意志・过去', 'green', '曾在'),
    'いません': ('没有・不在（人）', '存在・有意志・否定', 'green', '不在'),
    'います': ('有・在（人/动物）', '存在动词・有意志', 'green', '有'),
    'ちがいます': ('不是・不对', '动词・否定性应答', 'green', '不对'),
    'そうです': ('是这样', '应答・确认', 'green', '是这样'),
}
_PRED_ORDER = sorted(PREDICATES.keys(), key=len, reverse=True)

# ---------------------------------------------------------------- 动词活用（第5课起）
# 这里的活用形不是「独立谓语」，而是贴在动词词干后面的形态尾巴：
# 起き＋ます＝起きます。切成两块是为了让学习者看见「谓语中心＋末尾形态」，
# 与 です／あります 的处理一致；罗马音仍写成一个词（okimasu），不断空格。
# 值为 (中文词义, 形态说明, 下划线颜色, 直译行短词义)。
INFLECTIONS = {
    'ませんでした': ('（礼貌体・过去否定）', '动词・过去否定', 'green', '（过去否定）'),
    'しませんでした': ('（礼貌体・过去否定）', '动词・过去否定', 'green', '（过去否定）'),
    'ましょう': ('（礼貌体・意志）', '动词・意志形', 'green', '（意志）'),
    'しましょう': ('（礼貌体・意志）', '动词・意志形', 'green', '（意志）'),
    'ません': ('（礼貌体・否定）', '动词・否定', 'green', '（否定）'),
    'しません': ('（礼貌体・否定）', '动词・否定', 'green', '（否定）'),
    'ました': ('（礼貌体・过去）', '动词・过去', 'green', '（过去）'),
    'しました': ('（礼貌体・过去）', '动词・过去', 'green', '（过去）'),
    'ます': ('（礼貌体）', '动词・礼貌体', 'green', '（非过去）'),
    'します': ('做（礼貌体）', '动词・Ⅲ类（する）', 'green', '做'),
    'ください': ('请给我', '补助动词・命令形', 'green', '请'),
}
_INFLECT_ORDER = sorted(INFLECTIONS.keys(), key=len, reverse=True)
# 谓语与活用形合成一张「从长到短」的匹配表（各剥一次，长的优先）
_PRED_OR_INFLECT = tuple(sorted(set(PREDICATES) | set(INFLECTIONS),
                                key=len, reverse=True))
# する 系列（勉強します／買い物をしました）：尾巴前面接的是名词，不是一个动词词干
_SURU_INFLECTIONS = ('します', 'しました', 'しません', 'しませんでした', 'しましょう')


def verb_masu_form(stem_surf):
    """
    词干 → 词表里的「ます形」条目。教材词表按ます形收录动词（起きます／飲みます），
    所以还原方向是「词干 + ます」去查，而不是查辞书形。
    起き→起きます（动2）、働き→働きます（动1）、来→来ます（动3）
    """
    stem = (stem_surf or '').strip()
    if not stem:
        return ''
    info = LEXICON.get(stem + 'ます')
    if info and '动' in (info.get('pos') or ''):
        return stem + 'ます'
    return ''


def suru_verb_base(stem_surf):
    """
    「名词＋します」型复合动词的词干：勉強します → 勉強。
    只有词表里这个词条是 动3 才算——話します（話す，动1）走的是「話し＋ます」，
    不能被误认成「話＋します」。
    """
    stem = (stem_surf or '').strip()
    if not stem:
        return ''
    info = LEXICON.get(stem + 'します')
    if info and (info.get('pos') or '').strip() == '动3':
        return stem
    return ''


# ---------------------------------------------------------------- 形容词活用（第9课起）
# 教材词表按「〜い／〜な」收录形容词：辛い（形1）／静か（形2）。
# 与动词同理，活用尾巴切成独立块，让学习者看见「词干＋末尾形态」：
#     熱く＋ない＋です      → atsuku nai desu
#     楽し＋かった＋です    → tanoshikatta desu
#     静か＋な＋町（连体形）→ shizuka na machi
# 尾巴一律需要「剥完剩下的词干确实是词表里的形容词」才允许剥，
# 否则 ビル／なる／あなた 这类词尾偶合的假名会被切坏。
ADJ_I_TAILS = {
    'かった': {'zh': '（い形容词・过去）', 'note': 'い形容词・过去', 'color': 'green',
               'lit': '（过去）', 'glue': True},
    'なかった': {'zh': '（否定・过去）', 'note': '形容词・过去否定', 'color': 'green',
                 'lit': '（过去否定）', 'glue': False},
    'ない': {'zh': '（否定）', 'note': '否定形（ない）', 'color': 'green',
             'lit': '不', 'glue': False},
}
_ADJ_TAIL_ORDER = sorted(ADJ_I_TAILS.keys(), key=len, reverse=True)


def _adj_pos(surface, kind):
    """词表里是不是某类形容词（形1＝い形容词、形2＝な形容词）。"""
    info = LEXICON.get((surface or '').strip())
    return bool(info) and (info.get('pos') or '').startswith(kind)


def adj_i_ku_ok(head):
    """词干是不是 い形容词的连用形（熱く／高く／安く）：熱→熱い 在词表里。"""
    return bool(head) and len(head) > 1 and head.endswith('く') \
        and _adj_pos(head[:-1] + 'い', '形1')


def adj_i_stem_ok(head):
    """词干是不是 い形容词的词干（楽し／高か→高い）：head＋い 在词表里。"""
    return bool(head) and _adj_pos(head + 'い', '形1')


def adj_form(surface):
    """
    形容词活用形 → (词表里的辞书形, 形态说明后缀)。

    词表按辞书形收录，课文里出现的是活用形，所以查词义前先还原：
        熱く   → (熱い,   （连用形）)      熱くないです
        楽し   → (楽しい, （过去形词干）)  楽しかったです
        静かな → (静か,   （连体形）)      静かな町です
    查不到就返回空，交给普通查表——绝不猜词。
    """
    s = (surface or '').strip()
    if not s:
        return '', ''
    # な形容词：静かな（连体形）→ 静か
    if s.endswith('な') and len(s) > 1 and _adj_pos(s[:-1], '形2'):
        return s[:-1], '（连体形）'
    # い形容词连用形／过去形词干：熱く → 熱い、楽し → 楽しい
    # い形容词：连用形（熱く → 熱い）与过去形词干（楽し → 楽しい）
    if s.endswith('く') and len(s) > 1 and _adj_pos(s[:-1] + 'い', '形1'):
        return s[:-1] + 'い', '（连用形）'
    if _adj_pos(s + 'い', '形1'):
        return s + 'い', '（过去形词干）'
    return '', ''

def predicate_info(p):
    """谓语／活用形 → (中文词义, 形态说明, 颜色, 直译短词义)。"""
    if p in PREDICATES:
        return PREDICATES[p]
    if p in ADJ_I_TAILS:
        t = ADJ_I_TAILS[p]
        return (t['zh'], t['note'], t['color'], t['lit'])
    if p in TE_TAILS:
        t = TE_TAILS[p]
        return (t['zh'], t['note'], t['color'], t['lit'])
    return INFLECTIONS.get(p)


# 动词て形（第14课）：聞いて／読んで。切成「词干＋て」，让音便看得见。
TE_TAILS = {
    'て': {'zh': '（て形）', 'note': '动词・て形', 'color': 'green', 'lit': '（て）'},
    'で': {'zh': '（て形・浊音便）', 'note': '动词・て形（浊音便）', 'color': 'green',
           'lit': '（て）'},
}

# か／ね／よ 的前面若是动词活用形（休みました＋か / 飲みません＋か / 行きます＋か），
# 也允许把终助词切出来。否则「休みましたか」会被当成一个词，罗马音变成 yasumimashitaka。
_FINAL_AFTER = tuple(_PRED_ORDER) + (
    'ませんでした', 'ましょう', 'ません', 'ました', 'ます',
    'ください', 'でしょう', 'たい', 'ない')

# 敬称后缀：生成罗马音时与姓名断开，避免 risanwa 这种连写
_HONORIFIC = ['さん', 'くん', 'ちゃん', 'さま', 'たち']


# 罗马音里必须与词体断开的尾部成分（敬称 + 副助词）：
# 長島さんほど → nagashima san hodo、森さんだけ → mori san dake。
# 只收 2 字以上，避免把词尾偶合的假名误当成分。
_TAIL_WORDS = tuple(_HONORIFIC) + (
    'ほど', 'だけ', 'など', 'なんか', 'ばかり', 'くらい', 'ぐらい',
    'ごろ', 'ずつ', 'こそ', 'しか', 'より')
# 副助词（上面这一串）只在前半截确实是个词时才断：
#   りさん＋しか → ri san shika     （对，りさん 以敬称收尾）
#   おきま＋しか → 不断（教材数据把 ますか 误抄成 ましか，不能跟着切成 okima shika）
_SUB_TAILS = tuple(t for t in _TAIL_WORDS if t not in _HONORIFIC)
# 教材里把助词写成片假名的三种（第27・30・36课的 ヘ 是真实例子）
_KATA_PARTICLE = {'ヘ': 'へ', 'ヲ': 'を', 'ハ': 'は'}
# 断词器用的助词表：不含 か／や——词中的 か 多半是活用的一部分
# （楽しかった／わかりました），段尾的 か／や 交给第 3 步的助词剥离。
_SPLIT_PARTICLES = tuple(p for p in _PEEL_ORDER if p not in ('か', 'や'))
# 补助用言：時半です＋から → jihan desu kara、来てください → kite kudasai
_AUX_TAILS = ('です', 'でした', 'でしょう', 'ください')
_PARTICLE_ROMAJI = {'は': 'wa', 'へ': 'e', 'を': 'o', 'では': 'de wa', 'じゃ': 'ja'}

# 接续助词：挂在谓语之后，把前后两个小句连起来（好きです＋から／有料です＋が）。
# 它们只在「前面收在一个谓语上」时才被认出来，所以 これから／だから 这类词不会被切坏。
_CONJ_TAILS = ('から', 'が', 'けど', 'けれど', 'けれども')
# 谓语的收尾形态：接续助词前面必须是这些之一
_AUX_PRED_END = ('です', 'でした', 'でしょう', 'ます', 'ました', 'ません',
                 'ませんでした', 'ましょう', 'だ', 'ない', 'かった',
                 # て形也能带接续助词：聞いて＋から／書いて＋から（第14课）
                 'て', 'で')

_HONORIFIC_ZH = {'さん': '（敬称）', 'くん': '（君）', 'ちゃん': '（昵称）',
                 'さま': '（尊称）', 'たち': '们'}

# 人名＋さん 的中文译名，沿用教材自己的译法：
# 中国人用「小X」，日本人用「X先生」，已知女性用「X女士」。
# 机械地拼成「森（敬称）」在读起来像字典条目，不像课文。
NAME_ZH = {
    '李さん': '小李', '王さん': '小王', '張さん': '小张',
    '森さん': '森先生', '林さん': '林先生', '吉田さん': '吉田先生',
    '田中さん': '田中先生', '中村さん': '中村先生', '長島さん': '长岛先生',
    '佐藤さん': '佐藤先生', '鈴木さん': '铃木先生', '高橋さん': '高桥先生',
    '小野さん': '小野女士', 'スミスさん': '史密斯先生', '金さん': '金先生',
    '李秀麗さん': '李秀丽女士', '小野緑さん': '小野绿女士',
}

# 教材词性代码 → 可读标签。原代码（名/专/动1）对学习者是天书。
POS_LABEL = {
    '名': '名词', '专': '专有名词', '代': '代词', '疑': '疑问词',
    '连': '连体词', '副': '副词', '叹': '感叹词', '熟语': '固定搭配',
    '动1': '动词・Ⅰ类', '动2': '动词・Ⅱ类', '动3': '动词・Ⅲ类',
    '动': '动词', '形1': 'い形容词', '形2': 'な形容词', '形': '形容词',
    '名接': '接尾', '接': '接续词', '助': '助词', '感': '感叹词', '连体': '连体词',
}


# ---------------------------------------------------------------- 数量词（第13课）
# 教材把「数字＋量词」整块注音（三冊 さんさつ／七時間 しちじかん／一週間 いちしゅうかん），
# 词表只收量词或干脆不收，所以中文词义在这里合成：三冊→三本、七時間→七个小时。
# 读音一律以教材注音为准（这一层只管中文），所以这里不做读音合成。
_NUM_ZH = {'0': '零', '1': '一', '2': '二', '3': '三', '4': '四', '5': '五', '6': '六',
           '7': '七', '8': '八', '9': '九',
           '０': '零', '１': '一', '２': '二', '３': '三', '４': '四', '５': '五',
           '６': '六', '７': '七', '８': '八', '９': '九'}
COUNTERS = {
    '冊': '本', '枚': '张', '台': '台', '個': '个', '本': '根', '杯': '杯', '皿': '盘',
    '匹': '只', '人': '人', '歳': '岁', '円': '日元', '階': '层', '回': '次', '度': '度',
    '番': '号', '泊': '晚', '足': '双', '着': '件', '箱': '箱', '袋': '袋',
    '時間': '个小时', '週間': '周', 'か月': '个月', 'ヶ月': '个月', 'カ月': '个月',
    '日': '天', '年': '年', '分': '分', '秒': '秒', '月': '月', '週': '周',
}


def counter_gloss(surface):
    """「数字＋量词」→ 中文数量词：三冊→三本、七時間→七个小时、一週間→一周、1杯→一杯。"""
    m = re.match(r'^([0-9０-９一二三四五六七八九十百千万]+)(.+)$', surface or '')
    if not m:
        return None
    num, counter = m.group(1), m.group(2)
    if counter not in COUNTERS:
        return None
    return ''.join(_NUM_ZH.get(ch, ch) for ch in num) + COUNTERS[counter]


# 教材的 ! 标记是「注音汉字起点」，不是词边界：かばん!売(う)り!場(ば) 会被切成
# かばん／売り／場，罗马音就成了 kaban uri ba。下面的后缀白名单专门把这类
# 「送り仮名结尾的复合前项 + 单汉字后缀」重新黏回一个词（売り場 → uriba）。
COMPOUND_SUFFIX = set('場物人手口屋店側料代車所員館局形気先値込付番')
# お／ご 是敬语前缀，同样必须与后项黏成一个词（お粥 → okayu）
HONORIFIC_PREFIX = ('お', 'ご')


def _is_hira(ch):
    return '\u3041' <= ch <= '\u3096'


def _is_kata(ch):
    return '\u30a1' <= ch <= '\u30fa' or ch == 'ー'


def _has_kanji(s):
    return any('\u4e00' <= c <= '\u9fff' for c in s)


def _joins_compound(prev_surf, cur_surf):
    """
    判断 cur_surf 这个 ! 边界是否其实落在复合词内部，不该在罗马音里断空格。
    prev_surf 是「当前正在累积的这个词」的字面（可能已含多个 token，如「売り」）。
    """
    ps, cs = prev_surf or '', cur_surf or ''
    if not ps or not cs:
        return False
    # お粥／ご飯：敬语前缀直接黏
    if ps in HONORIFIC_PREFIX:
        return True
    # 送り仮名结尾的复合前项（売り・飲み・買い・入り…）+ 单汉字后缀（場・物・口…）
    if len(cs) == 1 and cs in COMPOUND_SUFFIX and _has_kanji(ps) and _is_hira(ps[-1]):
        return True
    return False


def group_tokens(tokens):
    """
    把 tokenize_raw 的输出按「　」与句读重新聚合成语块段。
    新标日在同一语块内可能用 ! 切出多个词（かばん!売(う)り!場(ば)は），
    必须合并成一个分析单位，否则会误判助词位置。

    每个语块段带两套粒度，各有用途：
      parts — 注音级细粒度，供前端拼 <ruby> 振假名
      words — ! 词级粒度，供罗马音断空格（注音级会把「かばん売り場」碎成 kaban u ri ba）
    """
    # 语块边界：基本课文用全角空格「　」分块；会话／应用课文的排版没有空格，
    # 这时退化为用 ! 注音词首当边界（! 只保证是「注音词首」，所以还要用
    # _joins_compound 把 かばん!売り!場 这类复合词黏回去）。
    break_on_wb = not any(t.get('sep') for t in tokens)
    segments = []
    cur = None
    cur_word_surf = ''
    for t in tokens:
        if t.get('sep'):
            if cur:
                segments.append(cur)
                cur = None
            cur_word_surf = ''
            continue
        if t.get('punct') is not None:
            if cur:
                segments.append(cur)
                cur = None
            segments.append({'surf': t['surf'], 'read': '', 'punct': t['punct'],
                             'kind': 'punct', 'parts': [], 'words': []})
            cur_word_surf = ''
            continue
        read = t.get('read', t['surf'])
        part = {'surf': t['surf'], 'read': read, 'ann': t.get('ann', False)}
        # 促音「っ」不能收词：教材用 ! 把「1(いっ)!杯(ぱい)」切成两块，
        # 但 いっぱい 是一个词，促音必须双写下一块的辅音（ippai，不是 it pai）。
        if cur is not None and break_on_wb and t.get('wb') \
                and not _joins_compound(cur['surf'], t['surf']) \
                and not (cur['read'] or '').endswith('っ'):
            segments.append(cur)
            cur = None
        if cur is None:
            cur = {'surf': t['surf'], 'read': read, 'kind': 'chunk',
                   'parts': [part], 'words': [read]}
            cur_word_surf = t['surf']
        else:
            cur['surf'] += t['surf']
            cur['read'] += read
            cur['parts'].append(part)
            if t.get('wb') and not _joins_compound(cur_word_surf, t['surf']) \
                    and not cur['words'][-1].endswith('っ'):
                cur['words'].append(read)
                cur_word_surf = t['surf']
            else:
                cur['words'][-1] += read
                cur_word_surf += t['surf']
    if cur:
        segments.append(cur)
    return segments


def _strip_tail(read, tail):
    """从假名读法尾部剥掉字面 tail 对应的读法（按最后一次出现定位）。"""
    if not tail:
        return read
    if read.endswith(tail):
        return read[:-len(tail)]
    idx = read.rfind(tail)
    return read[:idx] if idx > 0 else read


def analyze_segment(seg):
    """
    把语块段拆成四层：词体 body / 格助词 particle / 谓语 predicate / 终助词 final。
    剥离顺序至关重要：终助词在谓语之后 → 先剥终助词，再剥谓语，最后剥格助词。
      一階ですか   →  final=か, predicate=です,   body=一階
      学生では     →  particle=では,              body=学生
      犬がいますね →  final=ね, predicate=います, body=犬, particle=が
    """
    if seg['kind'] == 'punct':
        return seg

    # 教材排版偶尔把助词写成片假名（公園ヘ行きました／第27・30・36课共 3 处），
    # 只在段尾出现时归一成平假名，免得 ヘリコプター 这类词被误伤。
    surf = seg['surf']
    base_read = seg.get('read') or ''
    if surf and surf[-1] in _KATA_PARTICLE:
        canon = _KATA_PARTICLE[surf[-1]]
        surf = surf[:-1] + canon
        if base_read:
            base_read = base_read[:-1] + canon
    out = dict(seg)
    out['particle'] = None
    out['predicate'] = None
    # 谓词有两个槽：外层是 です／ではありません 这类，内层是形容词活用尾巴
    # （楽し＋かった／熱く＋ない）；conj 是谓语之后的接续助词（好きです＋から）。
    out['predicate_inner'] = None
    out['inner_inflection'] = False
    out['conj'] = None
    out['final'] = None
    # --- 1) 终助词 ---
    # か 只在「剥掉后剩下一个像样的谓语」时才认定（一階ですか → か + です；
    # 休みましたか → か + ました），否则会把「会社か」这类词尾误当疑问助词。
    # ね／よ 无此风险，直接剥。
    if surf not in NO_PEEL:
        for f in _FINAL:
            if not (surf.endswith(f) and len(surf) > len(f)):
                continue
            rest = surf[:-len(f)]
            if f == 'か' and not any(rest.endswith(p) for p in _FINAL_AFTER):
                continue
            if not rest or rest in NO_PEEL:
                continue
            out['final'] = f
            surf = rest
            break
    # --- 2) 接续助词：谓语之后的 から／が（森さんは お酒が 好きですから。／有料ですが）---
    # 只有当「剥掉它之后剩下的是一个谓语」时才认，所以 だから／これから 不会被切坏。
    if surf not in NO_PEEL:
        for c in _CONJ_TAILS:
            if surf.endswith(c) and len(surf) > len(c):
                head = surf[:-len(c)]
                if head.endswith(_AUX_PRED_END):
                    out['conj'] = c
                    surf = head
                    break

    # --- 3) 谓语／活用形 ---
    # 一次扫描、长的优先：ませんでした 必须先于 でした 命中，
    # 否则「働きませんでした」会被切成 働きません＋でした。
    # 独立谓语（です／あります／います）看词体像不像主语；
    # 活用尾巴要求剥完后剩下的词干是词表里的动词（起き→起きます）。
    for p in _PRED_OR_INFLECT:
        if not surf.endswith(p):
            continue
        head = surf[:-len(p)]
        if p in INFLECTIONS:
            if not head:
                # 「ください」可以单独成段：コーラと ケーキを ください。
                if p == 'ください':
                    out['predicate'] = p
                    out['inflection'] = True
                    surf = ''
                    break
                continue
            if p in _SURU_INFLECTIONS:
                ok = bool(suru_verb_base(head))       # 勉強します → 勉強＋します
            else:
                ok = bool(verb_masu_form(head))       # 起きます → 起き＋ます
            if ok:
                out['predicate'] = p
                out['inflection'] = True
                surf = head
                break
            continue
        if (head or p in ('あります', 'います', 'ありません', 'いません', 'です')) \
                and (p not in _EXISTENCE_PREDS or _existence_ok(surf, p)):
            out['predicate'] = p
            surf = head
            break

    # --- 4) 内层谓语尾：い形容词活用（楽しかった → 楽し＋かった／熱くない → 熱く＋ない）---
    # 外层（です／ではありません）剥完之后，剩下的词体可能还带着形容词的活用尾巴。
    # 尾巴一律要求「剥完剩下的词干确实是词表里的形容词」（熱く→熱い／楽し→楽しい），
    # 否则 ビル／なる／あなた 这类词尾偶合的假名会被切坏。
    # 「ない」只有两种情况允许剥：前面是 い形容词连用形（熱く），
    # 或者前面收在助词上（ことが ない／しか ない）；单独成段时它本来就是否定谓词。
    if surf and surf not in NO_PEEL:
        for p in _ADJ_TAIL_ORDER:
            if not surf.endswith(p) or len(surf) < len(p):
                continue
            head = surf[:-len(p)]
            if not head:
                ok = p in ('ない', 'なかった')
            elif p == 'かった':
                ok = adj_i_stem_ok(head)
            else:
                # ない／なかった：前面要么是 い形容词连用形（熱くない），
                # 要么收在助词上（ことがない／しか ない）。か／や 不算依据——
                # 它们是五段动词ない形的一部分（行かない／書かない），
                # 拿它们当证据会把 行かない 切成 行＋か＋ない。
                ok = adj_i_ku_ok(head) or head.endswith(_NEG_LEFT_PARTICLES)
            if not ok:
                continue
            out['predicate_inner'] = p
            out['inner_inflection'] = bool(ADJ_I_TAILS[p]['glue'])
            surf = head
            break

    # --- 4b) 动词て形（第14课）：聞いて＋から → 聞い＋て＋から ---
    # 与形容词同理，切成「词干＋て」让学习者看见音便（書い／読ん／まわっ／いっ）。
    # 只有「剥完的词干确实是词表里的动词」才允许剥，否则 あとで／それで 会被切坏。
    if surf and surf not in NO_PEEL:
        for p in ('て', 'で'):
            if not surf.endswith(p) or len(surf) <= len(p):
                continue
            head = surf[:-len(p)]
            if _te_stem_masu(head):
                out['predicate_inner'] = p
                out['inner_inflection'] = True     # て形与词干连写：聞いて → kiite
                surf = head
                break

    # 谓词与终助词剥掉之后，供助词判定用的读法
    mid_read = base_read
    for tail in (out['final'], out['conj'], out['predicate'], out['predicate_inner']):
        if tail:
            mid_read = _strip_tail(mid_read, tail)

    # --- 5) 格助词（仅段尾，且剥完后仍是合法词体） ---
    # 「剥完还是完整词」这一条不能省：とても／きっと／ちょっと 这类
    # 纯假名词的尾字与助词同形，剥了就会剩残干（とて / きっ）。
    if surf and surf not in NO_PEEL:
        for p in _PEEL_ORDER:
            if surf.endswith(p) and len(surf) > len(p):
                cand = surf[:-len(p)]
                if not _body_is_word(cand, _strip_tail(mid_read, p), p):
                    continue
                out['particle'] = p
                surf = cand
                break

    out['body'] = surf
    read = base_read
    for tail in (out['final'], out['conj'], out['predicate'],
                 out['predicate_inner'], out['particle']):
        if tail:
            read = _strip_tail(read, tail)
    out['body_read'] = read
    return out

def gloss_of(surface, prefer_verb=False):
    """
    取词义，返回 dict(zh, en, pos, honorific) 或 None。

    三处清洗，都是为了前端可读：
      1. 人名＋さん 走 NAME_ZH 专表（森さん→森先生），不用机械的"（敬称）"
      2. 教材词义的体例标记剥掉：「(大)学生」→「学生」、「（高级）公寓」→「公寓」
      3. 多义项只取第一个：「房间，屋子」→「房间」。直译行寸土寸金，不能塞两个词
    """
    surface = (surface or '').strip()
    if not surface:
        return None
    # 形容词活用形先还原成辞书形再查（熱く → 熱い、楽し → 楽しい、静かな → 静か）。
    # 这一步是「剥完的残干也得是个词」的另一面：词干必须真的指向词表里的形容词。
    dic, form_label = adj_form(surface)
    if dic:
        ainfo = LEXICON.get(dic)
        if ainfo:
            return {'zh': clean_gloss(ainfo.get('zh', '')), 'en': ainfo.get('en', ''),
                    'pos': POS_LABEL.get(ainfo.get('pos', ''), ainfo.get('pos', '')) + form_label,
                    'honorific': ''}
    if prefer_verb:
        # 段尾带活用尾巴时（休み＋ました／帰り＋ました），词干按动词解释，
        # 否则 休み／帰り 会命中同形的名词（休息／回程），词性标注也跟着错。
        dic = verb_masu_form(surface) or suru_verb_base(surface)
        if dic:
            # 名词＋します 型复合动词（買い物します）：词干就是那个名词
            vinfo = LEXICON.get(dic if dic.endswith('ます') else dic + 'します')
            if vinfo:
                return {'zh': clean_gloss(vinfo.get('zh', '')), 'en': vinfo.get('en', ''),
                        'pos': POS_LABEL.get(vinfo.get('pos', ''), vinfo.get('pos', '')) + '（ます形）',
                        'honorific': ''}
    for h in _HONORIFIC:
        if surface.endswith(h) and len(surface) > len(h):
            if surface in NAME_ZH:
                return {'zh': NAME_ZH[surface], 'en': '', 'pos': POS_LABEL['专'],
                        'honorific': h}
            stem = surface[:-len(h)]
            info = lookup(stem)
            if info and not info.get('partial'):
                return {'zh': clean_gloss(info.get('zh', stem)) + _HONORIFIC_ZH[h],
                        'en': info.get('en', ''),
                        'pos': POS_LABEL.get(info.get('pos', ''), info.get('pos', '')),
                        'honorific': h}

    info = lookup(surface)
    if not info:
        # ① 数量词：「数字＋量词」整块不在词表里（三冊／七時間／一週間）→ 合成中文
        cnt = counter_gloss(surface)
        if cnt:
            return {'zh': cnt, 'en': '', 'pos': '数量词', 'honorific': ''}
        # ② 动词ます形词干不是词表条目（起き → 起きます），用「词干＋ます」回查。
        #    这一步让「起き」「働き」「飲み」这些词干也能拿到正确词义。
        dic = verb_masu_form(surface)
        if dic:
            info = LEXICON.get(dic)
            if info:
                return {'zh': clean_gloss(info.get('zh', '')), 'en': info.get('en', ''),
                        'pos': POS_LABEL.get(info.get('pos', ''), info.get('pos', '')) + '（ます形）',
                        'honorific': ''}
        # ②b 名词＋します 型复合动词的词干（買い物 → 買い物します）
        suru = suru_verb_base(surface)
        if suru:
            sinfo = LEXICON.get(suru + 'します')
            if sinfo:
                return {'zh': clean_gloss(sinfo.get('zh', '')), 'en': sinfo.get('en', ''),
                        'pos': POS_LABEL.get(sinfo.get('pos', ''), sinfo.get('pos', '')) + '（します型）',
                        'honorific': ''}
        # ③ 动词的其它活用形（て形语干 書い／いっ、辞书形 いく／よむ）也按读法回查
        for face, label in ((_te_stem_masu(surface), '（て形词干）'),
                            (_masu_from_dic(surface), '（辞书形）')):
            if not face:
                continue
            tinfo = LEXICON.get(face)
            if tinfo:
                return {'zh': clean_gloss(tinfo.get('zh', '')), 'en': tinfo.get('en', ''),
                        'pos': POS_LABEL.get(tinfo.get('pos', ''), tinfo.get('pos', '')) + label,
                        'honorific': ''}
        return None
    # 七時間 会前缀命中 七時（7点）→ partial；数量词优先，别让「7点」顶掉「七个小时」
    if info.get('partial'):
        cnt = counter_gloss(surface)
        if cnt:
            return {'zh': cnt, 'en': '', 'pos': '数量词', 'honorific': ''}
    return {'zh': clean_gloss(info.get('zh', '')), 'en': info.get('en', ''),
            'pos': POS_LABEL.get(info.get('pos', ''), info.get('pos', '')),
            'honorific': '', 'partial': info.get('partial', '')}


_LEADING_PAREN = re.compile(r'^(\(|（)[^)）]*(\)|）)')
_LEADING_BRACKET = re.compile('^【[^】]*】')


def clean_gloss(zh):
    """剥掉教材词义的体例标记（（…）／【自】【他】），多义项只留第一个。"""
    if not zh:
        return zh
    s = _LEADING_BRACKET.sub('', zh).strip()
    s = _LEADING_PAREN.sub('', s).strip()
    for sep in ('，', '、', '；', ','):
        if sep in s:
            s = s.split(sep)[0].strip()
            break
    return s or zh


def _spaced_reading(read):
    """
    假名读法 → 罗马音，并在「尾部成分」前断开：
    敬称（りさん → ri san）与副助词（さんほど → san hodo）都要独立成词，
    否则罗马音会出现 nagashimasanhodo 这种连写。
    """
    from annot import kana_to_romaji
    for h in _HONORIFIC:
        # 敬称：只要前面还有字就断开（りさん → ri san）
        if read.endswith(h) and len(read) > len(h):
            return (_spaced_reading(read[:-len(h)]) + ' ' + kana_to_romaji(h)).strip()
    for h in _SUB_TAILS:
        # 副助词：前半截得是个真词（りさん＋しか），否则 おきましか 会被切坏
        if read.endswith(h) and len(read) - len(h) >= 2:
            rest = read[:-len(h)]
            if rest in KANA_WORDS or rest in KANA_READINGS \
                    or any(rest.endswith(w) for w in _KANA_TAILS):
                return (_spaced_reading(rest) + ' ' + kana_to_romaji(h)).strip()
    for h in _AUX_TAILS:
        # 补助用言（です／でしょう／ください）：前面还有 2 字以上就断开；
        # 「ん」是唯一的例外——ん＋です 是固定呼应（〜んです），必须断开成 n desu。
        if read.endswith(h) and (len(read) - len(h) >= 2
                                 or read[:-len(h)].endswith('ん')):
            return (_spaced_reading(read[:-len(h)]) + ' ' + kana_to_romaji(h)).strip()
    for h in _CONJ_TAILS:
        # 接续助词（谓语之后的 から／が）：前半截必须收在谓语上才断
        #   ことですから → koto desu kara、ゆうりょうですが → yuuryou desu ga
        #   これから → 前半截「これ」不是谓语，保持 korekara 不断
        if read.endswith(h) and len(read) - len(h) >= 2 \
                and read[:-len(h)].endswith(_AUX_PRED_END):
            return (_spaced_reading(read[:-len(h)]) + ' ' + kana_to_romaji(h)).strip()
    return kana_to_romaji(read)


def _ann_spans(seg, body):
    """词体读法里被「注音词」覆盖的区间，用于禁止在注音词内部断词。
    京都(きょうと) 是一个注音词，不能切成 kyou to；而 部屋(へや)には 里的
    に 是注音词之外的假名，可以断。"""
    spans = []
    pos = 0
    remain = len(body or '')
    for p in seg.get('parts', []):
        if remain <= 0:
            break
        r = p['read']
        if p.get('ann'):
            spans.append((pos, pos + len(r)))
        pos += len(r)
        remain -= len(p['surf'])
    return spans


def _trusted_left(piece, start, i, spans, particle):
    """
    断点左侧这一段够不够「一个完整的词」，用来决定要不要在助词前断空格。
      ① 就是词表里的词：へや／にんき
      ② 正好覆盖一个注音词：売り場(うりば)／手(て)（1 字的注音词也算词）
      ③ 注音词＋送假名，且末尾不是 ん／っ：ひっこし（引っ越し）
         末尾 ん 的必须排除，否则 読(よ)んで → yon de 这种动词て形会被切坏
      ④ 收在形式名詞上（見る|こと|が）——こと 是名词，后面当然能挂助词
      ⑤ 敬称收尾（りさん|は）与动词ます形语干（出し|に）也是真词
    注：「分(わ)からない」这种动词里的 から 由 _split_body_read 拦（から＋ない），
    不在这里判——这里只看左边够不够一个词。
    """
    if not piece:
        return False
    if piece in KANA_WORDS or piece in KANA_READINGS:
        return True
    if any(piece.endswith(t) for t in _FORM_NOUNS):
        return True
    # 敬称收尾是真词（りさん|は／もりさん|と），必须早于「末尾 ん 不切」那条——
    # 否则 李さんはテレビを 会连成 risanhaterebi。
    if any(piece.endswith(h) and len(piece) > len(h) for h in _HONORIFIC):
        return True
    # 动词ます形语干是真词（出し|に 行きます）——否则 出(だ)しに 会被整段留下。
    if VERB_KANA.get(piece + 'ます'):
        return True
    for a, b in spans:
        if a == start and b == i:
            return True
    # 「で／に／と」还可能是动词活用的一部分（いそいで／読んで／着いて），
    # 所以它们只认「整个就是词表里的词／整个就是注音词」这两种硬证据。
    if particle in ('で', 'に', 'と'):
        # 敬称结尾（りさん＋に／もりさん＋と）仍是硬证据，其余只认上面两种
        if not any(piece.endswith(h) and len(piece) > len(h) for h in _HONORIFIC):
            return False
        return True
    if piece[-1] in 'んっ':
        return False
    for a, b in spans:
        if start <= a and b <= i:
            return True
    return False


# 助词后面紧跟这些活用尾巴，说明它其实在动词内部：
#   あ|が|る（上(あ)がる）   みな|が|ら（見(み)ながら）   やす|も|う（休(やす)もう）
# 刻意只收多字尾巴与「必须成词」的单字（る／ら／う／ろ／ば）：
#   收了 ない／た／て／たく 会把 あいさつは ない、りょうりは たくさん、
#   ことは できません 这类「名词＋助词＋谓语」粘回去。动词里的 から
#   （分からない）另有专项规则，见 _split_body_read。
_VERB_TAIL_AFTER = ('ながら', 'たり', 'だり', 'たら', 'れば', 'ます', 'ました', 'ません',
                    'ましょう', 'たい', 'たかった', 'よう', 'おう',
                    'る', 'ら', 'う', 'ろ', 'ば')

# 复合形容词的固定尾巴：わかり|にくい、読み|やすい、食べ|すぎる。
# 它们前面接动词语干，尾巴内部的 に／く 与助词同形，所以在这里加一道守卫：
# 断点正好落在尾巴之前且左边是动词时，不许切（わか|り|に|くい 是错的）。
_COMPOUND_ADJ_TAILS = ('にくい', 'にくく', 'にくかっ', 'やすい', 'やすく', 'やすかっ',
                       'すぎる', 'すぎた', 'すぎて')


def _masu_from_dic(piece):
    """动词辞书形 → 词表里的词面（いく→行きます、よむ→読みます、あがる→上がります）。"""
    if len(piece) < 2:
        return ''
    table = {'う': 'い', 'く': 'き', 'ぐ': 'ぎ', 'す': 'し', 'つ': 'ち', 'ぬ': 'に',
             'ぶ': 'び', 'む': 'み', 'る': 'り'}
    i_kana = table.get(piece[-1])
    if not i_kana:
        return ''
    return VERB_KANA.get(piece[:-1] + i_kana + 'ます', '')


# 「行く」的て形是例外（いって，不是 いいて），靠这一条补上。
_TE_WHITELIST = {'いっ': 'いきます'}


def _te_stem_masu(head):
    """
    动词て形语干 → 词表里的词面（書い→書きます、読ん→読みます、いっ→行きます）。
    顺序很重要：先查白名单（行く 的 いって 是例外），再查**词面**（带汉字的语干
    如 言っ／買っ 直接拼出 言います／買います，比读法可靠），最后才查读法。
    """
    if not head:
        return ''
    face = _TE_WHITELIST.get(head)
    if face and VERB_KANA.get(face):
        return VERB_KANA[face]
    last = head[-1]
    if last == 'い':
        suffs = ['き', 'ぎ']                       # 書い／泳い（く・ぐ 的イ音便）
    elif last == 'っ':
        suffs = ['い', 'ち', 'り']                 # 買っ／待っ／取っ
    elif last == 'ん':
        suffs = ['み', 'に', 'び']                 # 読ん／死ん／遊ん
    elif last == 'し':
        suffs = ['']                               # 話して／消して（する）
    elif last == 'き':
        suffs = ['']                               # 来て
    else:
        suffs = []
    for suf in suffs:
        wface = head[:-1] + suf + 'ます'
        info = LEXICON.get(wface)
        if info and '动' in (info.get('pos') or ''):
            return wface
def _verb_form_ok(piece):
    """这一截是不是动词的活用形（ます形语干／て形语干／辞书形）——「〜ん」断点与
    复合形容词尾巴（わかり|にくい）靠它把关。假名要用 VERB_KANA 反查（词表按汉字收录）。"""
    return bool(verb_masu_form(piece) or _te_stem_masu(piece) or _masu_from_dic(piece)
                or VERB_KANA.get(piece + 'ます'))
    return ''




# 「でしょう」里的 で 不是助词（是断定助动词的一部分），断词时必须跳过
_NO_BREAK_AT = ('でしょう', 'でしょうか', 'です', 'でした', 'ます', 'ました',
                'ません', 'ましょう', 'ください')


# 形式名詞：只能跟在谓语之后，所以「左边收在谓语形上」本身就是断词依据——
# 不必要求左边是词表里的词。見ることが → miru koto、読んだことがある → …ta koto。
#   こと／もの  抽象名词化（第20课起）
#   とき／ところ／ため／はず／わけ／つもり／ほう  时间・场所・原因・推测・打算
_FORM_NOUNS = ('こと', 'もの', 'とき', 'ところ', 'ため', 'はず', 'わけ', 'つもり', 'ほう')
# 补助动词：跟在 形式名詞 或 て形 之后，意义已经虚化（〜ことになる／行っている）。
# 注意不收「する」系列（して／した／します）：那些是段级谓语，硬收会把
#     したい → shita i、さがして → saga shite 这种词内假名切开。
#     它们要断时由 _spaced_reading 的 _AUX_TAILS 处理（ことですから → koto desu kara）。
_AUX_VERBS = ('なって', 'なった', 'なり', 'なる', 'いる', 'いた', 'いく', 'いった',
              'くる', 'きた', 'ある', 'あった', 'おく', 'みる', 'しまう',
              'くれる', 'もらう', 'あげる', 'できる', 'ください')
# 谓语形收尾的假名：形式名詞前面的断点靠它把关。
#   まわる|こと ✓（る）   たべ|もの ✗（べ 不在表里 → tabemono 不切）
_PRED_END_KANA = set('うくぐすつぬぶむるたてでん')


def _pred_like_left(piece):
    """左边这一截收在谓语形上吗——形式名詞只能接在谓语之后。"""
    if len(piece) < 2:
        return False
    if piece[-1] in _PRED_END_KANA:
        return True
    if piece.endswith(('ない', 'たい', 'です', 'ます', 'ました', 'ません', 'かった')):
        return True
    # 形容词的连体形也能接形式名詞：いい|ところ、たいせつな|こと
    # 连体词同理：そんな|はず、この|つもり
    dic, _form = adj_form(piece)
    return bool(dic) or _adj_pos(piece, '形1') or _adj_pos(piece, '连')


def _aux_left_ok(piece):
    """补助动词前面要么是形式名詞（こと|になる），要么是「名词＋助词／て形」（にんきが|ある）。"""
    if not piece or len(piece) < 2:
        return False
    if any(piece.endswith(t) for t in _FORM_NOUNS):
        return True
    for p in _PEEL_ORDER:
        if piece.endswith(p) and len(piece) > len(p):
            base = piece[:-len(p)]
            # 助词前面得真是一个词：にんき|が|ある ✓ ／ さが|して ✗（さが 不是词）
            if any(base.endswith(t) for t in _FORM_NOUNS):
                return True
            return base in KANA_WORDS or base in KANA_READINGS
    return piece.endswith(('て', 'で'))


def _split_body_read(read, spans):
    """
    把词体读法按「词／助词」切开，只在有词表依据时动手：
      へやに            → heya ni
      ちゅうごくでとても → chuugoku de totemo
      みること          → miru koto        （形式名詞：左边收在谓语形上）
      いくことになって  → iku koto ni natte（补助动词：左边是形式名詞／助词）
    整段本身就是词表里的词（とても／きっと／たしか）时一律不切，
    断点也不许落在注音词内部（京都 是一个词）。
    三条依据都必须落在「另一侧也能说通」上，否则宁可不断：
      * 形式名詞前：左边必须是谓语形（べ 结尾的 たべもの 不切）
      * 补助动词前：左边必须是形式名詞或助词／て形
      * 助词前：左边必须是一个完整的词（见 _trusted_left）
    """
    if len(read) < 3:
        return [read]
    if read in KANA_WORDS or read in KANA_READINGS:
        return [read]
    for a, b in spans:
        if a == 0 and b >= len(read):
            return [read]

    def in_span(i):
        return any(a < i < b for a, b in spans)

    def in_ann(i):
        """i 落在某个注音词内部（含起点）——注音词是一个整词，绝不能在里头切。"""
        return any(a <= i < b for a, b in spans)

    out = []
    start = 0
    i = 0
    while i < len(read):
        hit = None
        done = False
        # でしょう／でしょうか 的「で」是断定助动词的一部分，不是助词
        if any(read.startswith(t, i) for t in _NO_BREAK_AT):
            i += 1
            continue
        # ⓪ 断点不许落在词表里的词内部：おととい 是一个词，不能被 と 切开
        #   （最长匹配优先；只有 read 从 start 开始真的等于这个词才算依据）
        if i > start and any(read.startswith(w, start) and start + len(w) > i
                             for w in _LONG_TAILS):
            i += 1
            continue
        # ⓪b 复合形容词尾巴（わかり|にくい）也是词内，不许在它前面切
        if i > start and _verb_form_ok(read[start:i]) \
                and any(read.startswith(t, i) for t in _COMPOUND_ADJ_TAILS):
            i += 1
            continue
        # ⓪ 「〜ん」单独成片：行(い)くん ですか → iku n desu（左边必须是动词）
        if read[i:i + 1] == 'ん' and i + 1 == len(read) and i > start \
                and _verb_form_ok(read[start:i]):
            out.append(read[start:i])
            out.append('ん')
            i += 1
            start = i
            continue
        # ① 形式名詞（こと／もの／とき…）：左边收在谓语形上才切
        for t in _FORM_NOUNS:
            if not (read.startswith(t, i) and not in_ann(i)):
                continue
            left = read[start:i]
            if not _pred_like_left(left):
                continue
            if (left + t) in KANA_READINGS:
                continue                  # かい|もの＝買い物 本来就是词，不能切
            if i + len(t) < len(read) and read[i + len(t)] in 'っゃゅょ':
                continue                  # ちゅう|はずっと：はず 只是 ずっと 的前半，不能切
            hit = t
            break
        # ② 补助动词（なって／いく／いる…）：左边是形式名詞／助词／て形才切
        if not hit:
            for t in _AUX_VERBS:
                if not (read.startswith(t, i) and not in_ann(i)):
                    continue
                left = read[start:i]
                if left and _aux_left_ok(left):
                    hit = t
                    break
                if not left and out and _aux_left_ok(read[:i]):
                    # 补助动词正好落在一片开头（いくこと|に|なって）：让它自成一片
                    out.append(t)
                    i += len(t)
                    start = i
                    done = True
                    break
        if done:
            continue
        # ③ 助词：左边必须是一个完整的词（原有的硬依据）
        #   三条前置否决：① 断点是某个注音词的起点（かい|もの 的 も 是 物(もの) 的首音）
        #                 ② 助词后面跟着活用尾巴（あ|が|る、みな|が|ら、やす|も|う）
        #                 ③ 断点贴着注音词的起点（同 ①，兜住 span 边界）
        #   先按「本片之内」（start..i）判，判不过再看累计读法——
        #   累计那一路是给「いくこと|に」这种跨片情况留的（こと 后面当然能挂助词）。
        if not hit:
            for p in _SPLIT_PARTICLES:
                if not read.startswith(p, i) or in_span(i):
                    continue
                # ① 断点正好是某个注音词的起点 → 这个「助词」是那个词的读音
                #    （かい|もの 的 も 是 物(もの) 的首音，不是助词 も）
                if any(a == i for a, _b in spans):
                    continue
                # ② 助词后面跟着活用尾巴 → 它在动词内部
                #    （あ|が|る 上がる、みな|が|ら 見ながら、やす|も|う 休もう）
                if any(read.startswith(t, i + len(p)) for t in _VERB_TAIL_AFTER):
                    continue
                if p == 'から' and read.startswith(('ない', 'なかっ'), i + 1):
                    continue      # 分からない 的 から 藏在动词里，不是助词
                left = read[start:i]
                ok = bool(left) and _trusted_left(left, start, i, spans, p)
                # 累计那一路只给「本片为空」的跨片情况留（いくこと|に|なって）：
                # 否则 そんなはず|は 会被切成 …はず|は。
                if not left and _trusted_left(read[:i], 0, i, spans, p):
                    ok = True
                if not ok:
                    continue
                hit = p
                break
        if hit:
            out.append(read[start:i])
            out.append(hit)
            i += len(hit)
            start = i
        else:
            i += 1
    out.append(read[start:])
    return [x for x in out if x]


def _emit_piece(piece):
    """断词切出来的一片：如果它就是助词（へやに → へや／に），按助词读音转写。"""
    if piece in _PEEL_ORDER and _PARTICLE_ROMAJI.get(piece):
        return _PARTICLE_ROMAJI[piece]
    return _spaced_reading(piece)


def segment_romaji(seg):
    """
    生成语块段罗马音。词体按 ! 词界断空格，助词与谓语各自独立成词。
    「では」必须转成 de wa 而非 deha——这里的 は 是助词。
    """
    parts = []
    body_read = seg.get('body_read') or ''
    words = seg.get('words') or []
    spans = _ann_spans(seg, seg.get('body') or '')

    if body_read and len(words) > 1:
        # 词体只覆盖前若干个词：从头顺次扣减，保住 ! 给出的词界；
        # 每个词内部再按助词切一次（ひっこしは → hikkoshi／wa）。
        remain = body_read
        off = 0
        for w in words:
            if not remain:
                break
            if remain.startswith(w):
                local = [(max(a, off) - off, min(b, off + len(w)) - off)
                         for a, b in spans if a < off + len(w) and b > off]
                for piece in _split_body_read(w, local):
                    parts.append(_emit_piece(piece))
                off += len(w)
                remain = remain[len(w):]
            else:
                # 词界对不上（词体被剥掉谓语之后 words 不再对齐，或教材没给 ! 词界）：
                # 一律交给「词表依据」断词器——它比教材的 ! 更准：
                #   かいもの 是一个词（注音起点规则挡住 かい|もの）
                #   あいさつは 要断成 あいさつ|は（は 是助词）
                local = [(max(a, off) - off, min(b, off + len(remain)) - off)
                         for a, b in spans if a < off + len(remain) and b > off]
                for piece in _split_body_read(remain, local):
                    parts.append(_emit_piece(piece))
                off += len(remain)
                remain = ''
    elif body_read:
        # 排版没有全角空格时，词体里可能还黏着助词（部屋には → heya ni wa）。
        # 按注音结构＋词表依据断开，切不动就整段保留。
        for piece in _split_body_read(body_read, spans):
            parts.append(_emit_piece(piece))

    if seg.get('particle'):
        p = seg['particle']
        pro = _PARTICLE_ROMAJI.get(p) or _spaced_reading(p)
        if body_read and (body_read + p) in KANA_WORDS and parts:
            # とても／ちゃんと／こんにちは：整体是词表里的一个词，不为尾字断空格
            parts[-1] += pro
        else:
            parts.append(pro)
    if seg.get('predicate_inner'):
        # 内层谓语尾（い形容词活用）：楽し＋かった → tanoshikatta（连写）、
        # 熱く＋ない → atsuku nai（ない 是独立的否定词，断空格）
        pro = _spaced_reading(seg['predicate_inner'])
        if seg.get('inner_inflection') and parts:
            parts[-1] += pro
        else:
            parts.append(pro)
    if seg.get('predicate'):
        pro = _spaced_reading(seg['predicate'])
        if seg.get('inflection') and parts:
            # 动词活用尾巴是词的一部分：起き＋ます 写成 okimasu，不断空格
            parts[-1] += pro
        else:
            parts.append(pro)
    if seg.get('conj'):
        # 接续助词（谓语之后的 から／が）：好きですから → suki desu kara
        parts.append(_spaced_reading(seg['conj']))
    if seg.get('final'):
        parts.append(_spaced_reading(seg['final']))
    return ' '.join(x for x in parts if x)


def analyze_sentence(jp_raw):
    """
    整句分析入口。
    返回 {'segments': [...], 'clean': 纯文本, 'romaji': 整句罗马音}
    """
    segs = group_tokens(tokenize_raw(jp_raw))
    analyzed = []
    romaji_parts = []
    clean_parts = []
    for s in segs:
        a = analyze_segment(s)
        analyzed.append(a)
        if a['kind'] == 'punct':
            romaji_parts.append(a['punct'])
            clean_parts.append(a['surf'])
        else:
            romaji_parts.append(segment_romaji(a))
            clean_parts.append(a['surf'])

    romaji = ''
    for p in romaji_parts:
        if p in ('.', ',', '!', '?', ';', ':', '...'):
            romaji = romaji.rstrip() + p
        else:
            romaji += (' ' if romaji and not romaji.endswith(' ') else '') + p
    return {'segments': analyzed, 'clean': ''.join(clean_parts),
            'romaji': re.sub(r'\s+', ' ', romaji).strip()}


def render_text(raw):
    """
    把 ! 标注明文渲染成前端可用的三种形态。

    输入：'!李(り)さんは\u3000!中国人(ちゅうごくじん)です。'
    输出：{'clean': '李さんは　中国人です。',
           'ruby' : '<ruby>李<rt>り</rt></ruby>さんは　<ruby>中国人<rt>ちゅうごくじん</rt></ruby>です。',
           'romaji': 'ri san wa  chuugokujin desu.'}

    clean 保留全角空格作为语块分隔，与 lessons.json 的 jp_clean 保持一致；
    romaji 在语块之间留双空格，视觉上对得上语块切分。
    """
    tokens = tokenize_raw(raw)
    clean_parts = []
    ruby_parts = []

    for t in tokens:
        if t.get('sep'):
            clean_parts.append(t['surf'])
            ruby_parts.append(t['surf'])
            continue
        if t.get('punct') is not None:
            clean_parts.append(t['surf'])
            ruby_parts.append(t['surf'])
            continue
        clean_parts.append(t['surf'])
        if t.get('ann'):
            ruby_parts.append('<ruby>%s<rt>%s</rt></ruby>' % (t['surf'], t['read']))
        else:
            ruby_parts.append(t['surf'])

    # 罗马音单独走一遍：按语块段生成，段间双空格。
    # 不能复用上面的循环——那个循环的粒度是注音 token，会把句读重复计入。
    romaji_parts = []
    for seg in group_tokens(tokens):
        if seg['kind'] == 'punct':
            romaji_parts.append(seg['punct'])
        else:
            romaji_parts.append(segment_romaji(analyze_segment(seg)))
            romaji_parts.append('  ')

    romaji = ''.join(romaji_parts)
    # 句读前的空格去掉，句读后补一个空格，最后压缩多余空白
    romaji = re.sub(r'\s+([.,!?;:])', r'\1', romaji)
    romaji = re.sub(r'([.,!?;:])(?=\S)', r'\1 ', romaji)
    romaji = re.sub(r'\s+', ' ', romaji).strip()
    return {'clean': ''.join(clean_parts), 'ruby': ''.join(ruby_parts), 'romaji': romaji}
