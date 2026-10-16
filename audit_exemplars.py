# -*- coding: utf-8 -*-
"""
audit_exemplars.py — 透视图数据的常驻审计器

背景：用户是初学者，不该承担替引擎找语法错误的责任。
本审计器把"用户圈出来一个才修一个"变成"整类错误一次扫干净"，
并且关键检查会同步进 build_exemplars_auto.py 的自检，回归即构建失败。

检查的错误类别（每一类都曾在真实数据里出现过或属于同族风险）：
  C1  连体/并列助词被当词尾格助词（の/と/や 拍平嵌套/并列）——用户两次圈出的病根
  C2  谓语没被切出来（动词/形容词尾留在词体里）
  C3  助词误剥（剥完后词体不是完整词，gloss 只能靠前缀残配）
  C4  汉字没有振假名（初学者看到裸汉字）
  C5  罗马音误读（は→ha、では→deha、汉字直转等）
  C6  词义残留教材体例或为空
  C7  下划线颜色与助词角色不一致
  C8  直译行 token 悬空 / 空 token / 小句为空
  C9  零主语推理与 が/は 显隐规则矛盾（含箭头锚点是否存在）
  C10 基本课文覆盖不全或句面与教材不一致
  C12 零主语箭头锚点语义错误（钉在宾语/方向等论元块上，而非话题块或谓语块）
  C13 面向初学者的中文字段里残留英文（词注/助词名/tooltip/直译行）


  C14 数据层罗马音（全 48 课）：由假名注音重生成，与 lessons.json 同步；
      无残留假名/汉字、无助词读音误读（は→wa／へ→e／を→o）；
      并对照回归用例表 ROMAJI_CASES——每一行对应一个真实修过的错误类别
      （拗音词干、促音、とても／ほど 类纯假名词、终助词独立成词、
        注音里的全角空格占位、存在动词与 〜ました 同形）。

  C15 教材内部注音一致性（**只报不拦**）：同一注音片段（汉字串＋紧跟的送假名）
      在全书出现不同注音时，先自动分出「合法多音（白名单）」与「已由
      build_romaji.SOURCE_PATCHES 修订的错字」，剩下的逐条列出供人工判读。
      这一项不写 problems、不影响 exit code——判读权在人，机器只把候选摆出来。
      （上一轮它只是 scratch 里的扫描脚本；入库当场又找出两处漏掉的错字。）
用法：python audit_exemplars.py            # 只报问题
      python audit_exemplars.py --dump     # 额外打印全量逐句明细供人工复读
"""

import io
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, 'content'))

import morphology as M  # noqa: E402

EXEMPLARS = os.path.join(HERE, 'data', 'exemplars.json')
LESSONS = os.path.join(HERE, 'data', 'lessons.json')

KANJI = re.compile(r'[一-鿿]')
LINKERS = {'の', 'と', 'や'}
PRED_TAILS = ('ます', 'です', 'ません', 'ました', 'ない', 'かった',
              'たい', 'てください', 'ましょう', 'だ', 'である')
PALETTE = {'blue', 'cyan', 'orange', 'red', 'purple', 'yellow',
           'green', 'magenta', 'teal', 'pink', 'indigo', 'brown', 'slate',
           'none', 'normal'}   # normal = 直译行里"不着色"的合法值
LATIN_WORDS = re.compile(r'[A-Za-z]{2,}')
# 允许出现在中文文案里的拉丁字母：
#   JC — 教材专有名词 JC企画 的原文缩写
#   wa — は 的读音说明「读作 wa」，这是必须写出来的语音事实
EN_WHITELIST = {'JC', 'wa', 'CD'}
# 格助词：带这些助词的块一定是论元（主语/宾语/方向/场所…），不可能是"隐性主语"
# 的合法落点。から 不在此列——它既可是格助词（起点）也可是接续助词（原因），
# 后者恰恰挂在谓语上（雨だから），由 looks_predicate 判别。
CASE_PARTICLES = {'が', 'を', 'に', 'へ', 'と', 'で', 'まで', 'の', 'や'}
# 谓语线索：词下注释里的词性词，或词尾的活用形
PRED_HINT = ('动词', '断定', '形容', 'て形', '过去形', '存在', '助动词')
PRED_TAILS_EXTRA = ('て', 'で', 'だ', 'る', 'た', 'いく', 'いる', 'ある',
                    'する', 'くる', 'なる', 'せる', 'れる', 'たい')


# 形式名词尾：它们不承担实义，只把前面的谓语收拢成一个整体（C3 用到）
_FORM_NOUN_TAILS = ('こと', 'もの', 'ほう', 'まえ', 'あと', 'とき', 'ところ', 'ため',
                    'の', 'つもり', 'はず', 'ばかり', 'よう', 'ほど', 'まま', 'わけ')


def _c3_acceptable(body):
    """C3 的两种合法情形（不是词义缺口）：
      ① 引号里的整句（「タバコを吸うな」）——它是引用内容，本来就不是词条；
      ② 「完整词＋形式名词」（フリーズする＋こと）——两半都查得到，
         只是引擎把它判成段内切片、段体没拆开。
    """
    if body.startswith(('「', '『')):
        return True
    for fn in sorted(_FORM_NOUN_TAILS, key=len, reverse=True):
        if body.endswith(fn) and len(body) > len(fn):
            hg = M.gloss_of(body[:-len(fn)]) or {}
            if hg.get('zh') and not hg.get('partial'):
                return True
            break
    return False


# 词体后面只跟了一个活用尾/接续助词时（いろいろ＋な、おいしい＋し、フリーズ＋する…），
# 说明词体本身是完整的——前缀残配剩下的那点尾巴不是"另一个词"，不算词义缺口。
_PARTIAL_FORM_TAILS = ('な', 'し', 'だ', 'だし', 'そう', 'する', 'した', 'して')


def _partial_is_form_tail(rest):
    """前缀残配剩下的尾巴是不是一个活用尾/接续助词。"""
    rest = (rest or '').strip()
    return bool(rest) and rest in _PARTIAL_FORM_TAILS


def looks_predicate(c):
    """
    判断一个 chunk 是不是谓语块（而不是名词论元块）。
    引擎产物用 kind 明确标注（谓语块 kind='predicate'，词体 kind='body'）；
    第 5 课以后动词词体的 gloss_sub 里也带"动词"字样（动词・Ⅰ类（ます形）），
    所以不能再只靠词性线索判断，否则词体会被误当成谓语。
    手写旧数据（没有 kind）继续走形态线索。
    """
    if c.get('kind') in ('predicate', 'final'):
        return True
    if c.get('kind'):
        return False


    sub = c.get('gloss_sub') or ''
    if any(h in sub for h in PRED_HINT):
        return True
    if (c.get('particle') or '') in ('', '、'):
        txt = c.get('text') or ''
        if txt.endswith(PRED_TAILS) or txt.endswith(PRED_TAILS_EXTRA):
            return True
    return False

problems = []


def flag(ex_id, code, msg):
    problems.append((ex_id, code, msg))


def chunk_units(c):
    if c.get('jp_units'):
        return c['jp_units']
    if c.get('ruby_parts'):
        return [{'type': 'ruby', 'kanji': p['kanji'], 'kana': p['kana']} for p in c['ruby_parts']]
    if c.get('ruby'):
        return [{'type': 'ruby', 'kanji': c['text'], 'kana': c['ruby']}]
    return [{'type': 'ruby', 'kanji': c['text'], 'kana': ''}]



def check_phrase_components(eid, comps):
    """C3 用：短语的每个成分都要查得到完整词义。

    成分本身还是短语时要递归下去——「この＋コンピュータの＋操作」这种折了两次的
    短语，内层成分的 body 是「このコンピュータ」（两个词拼起来的字面），
    拿它去查词表只能前缀残配，但那不代表成分有问题。
    """
    for comp in comps or []:
        if comp.get('components'):
            check_phrase_components(eid, comp['components'])
            continue
        cg = M.gloss_of(comp.get('body') or '')
        if cg is None or cg.get('partial'):
            flag(eid, 'C3', '短语成分「%s」查不到完整词义' % comp.get('body'))

def time_topic_adverbial(chunks, topic_ids, target):
    """第19／22课：时间名词做话题时是状语，不是主语（判据与引擎侧一致）。

    引擎在 build_exemplars_auto._time_topic_adverbial 里有同一条规则：
    话题是时间名词、且句尾不是名词谓语（です／だ 前是名词）时，
    真正的主语（我）隐在后台，Ø が 应该落在谓语块上。
    """
    try:
        import build_exemplars_auto as BA
        time_topics = set(BA.TIME_TOPICS)
    except Exception:
        return False
    topic = next((c for c in chunks if c['id'] in topic_ids), None)
    if topic is None or (topic.get('text') or '') not in time_topics:
        return False
    # 句尾是断定（です／だ）时，时间名词可能真的兼任主语（今日は 曇りだ），不豁免
    return '断定' not in (target.get('gloss_sub') or '')


def quote_speaker_subject(chunks, target=None):
    """第24课：と 引用＋思う 时，主句主语是说话人，Ø が 落在谓语块上而不是话题块。

    「李さんは 来ると 思います」＝我想小李会来——は 标的话题属于从句，
    把它当主句主语会教成"小李在想"。判据与引擎侧 _quote_marker 一致：
    句中有「と：引用」标记，且句中出现了 思う／考える 系的谓语。
    """
    if not any('と：引用' in (c.get('gloss_sub') or '') for c in chunks):
        return False
    if target is not None and not looks_predicate(target):
        return False
    return any((c.get('text') or '').startswith(('思い', '思う', '思っ', '考え')) for c in chunks)


def audit(ex):
    eid = ex['id']
    chunks = ex.get('chunks') or []
    ids = {c['id'] for c in chunks}
    # 课文「简单图」（simple: true）：只有 词块＋助词框＋振假名，
    # 没有词义／直译行／心法／零主语——所以按词义与直译打分的检查一律跳过，
    # 只保留与"看得见的成分"有关的检查：C1 拍平、C2 谓语切分、C4 振假名、C5 罗马音、C7 颜色、C17 字段越界。
    simple = bool(ex.get('simple'))
    # 谓语块：引擎产物看 kind；手写旧数据没有 kind，退回词性线索
    pred_chunks = {c['id'] for c in chunks
                   if c.get('kind') == 'predicate'
                   or (not c.get('kind') and c.get('gloss_sub')
                       and ('存在动词' in c['gloss_sub'] or '断定' in c['gloss_sub']
                            or '否定' in c['gloss_sub'] or '动词' in c['gloss_sub']))}

    for idx, c in enumerate(chunks):
        body = c.get('text') or ''
        part = c.get('particle') or ''

        # ---- C1 连体/并列助词被当词尾格助词 ----
        if part in LINKERS:
            nxt = chunks[idx + 1] if idx + 1 < len(chunks) else None
            nxt_is_pred = bool(nxt) and nxt['id'] in pred_chunks
            if part == 'の':
                # の 收尾只允许两种情形：名词化（后接谓语块，スミスさんの です）
                # 与句尾的终助词用法（どうしたの？——课文对白里极常见，后面没有别的块）。
                # 只有"后面还有成分、且那个成分不是谓语"时，才说明嵌套短语被拍平。
                if nxt is not None and not nxt_is_pred:
                    flag(eid, 'C1', 'の 作为词尾助词挂在「%s」上且后接非谓语块——嵌套短语被拍平' % body)
            else:
                # と/や 收尾本身合法（伴随用法，如 森さんと日本へ）。
                # 只有当后一块带着 が/は/も/を 却又不是谓语时，才说明是"漏合并的并列"。
                # 例外：已经折成一个短语块的并列（ビールと 日本酒と，どちらが…）——
                #   重复出现的 と 是并列短语自己的收尾标记，不是漏合并。
                nxt_part = (nxt or {}).get('particle') or ''
                if nxt and nxt_part in {'が', 'は', 'も', 'を'} and nxt['id'] not in pred_chunks \
                        and not c.get('phrase'):
                    flag(eid, 'C1', '%s 挂在「%s」上且后接「%s+%s」——疑似漏合并的并列短语'
                         % (part, body, nxt.get('text'), nxt_part))

        # 谓语／终助词／接续助词块不是名词词体：它们没有「词义」可查，
        # 也不该被要求「以谓语尾结尾」（它们本身就是谓语尾）。C2/C3 统一跳过。
        infl_chunk = (c['id'] in pred_chunks
                      or c.get('kind') in ('predicate', 'final', 'conj')
                      or '终助词' in (c.get('gloss_sub') or '')
                      or '接续助词' in (c.get('gloss_sub') or ''))

        # ---- C2 谓语没被切出来（只约束引擎产物；手写旧样例动词整块是既有风格） ----
        # 例外：词汇化的固定表达（すみません＝对不起／かしこまりました＝我知道了）、
        # 副词（まだ／きっと）都已经被冻结成一个词，拆开教反而错。
        # 简单图不带 gloss_sub，所以要**回词表问词性**，不能只看块上的标注。
        c2_sub = c.get('gloss_sub') or ''
        c2_lex = (M.gloss_of(body) or {}).get('pos') if body else ''
        # 简单图（课文）放宽口径：它的硬指标是"助词必须看得见"。
        # 因此只有**格助词被吞进块里**才算硬伤（「お年寄りの荷物を持ってあげました」
        # 这种把 を／の 一起粘掉的情况）；纯动词活用形整块（知っています／多くなりました）
        # 在简单图里可以接受——它没有藏起任何助词。
        c2_swallowed = any(ch in body for ch in 'がをにへでとはもやの')
        # 完整活用形／完整形容词整块是允许的：它没藏起任何助词，切开反而教错。
        #   危ない 是一个完整的い形容词（切开成 危な｜ない 会被读成否定形）；
        #   にげられました 是一个完整的受身形；引号里的整句本来就是引用内容。
        c2_sub_full = c2_sub or ''
        c2_whole_form = ('い形容词' in c2_sub_full or 'い形容词' in (c2_lex or '')
                         or '受身' in c2_sub_full or '受身' in (c2_lex or '')
                         or '敬语' in c2_sub_full or '谦让语' in c2_sub_full
                         or body.startswith(('「', '『')))
        if ex.get('auto_generated') and body and body.endswith(PRED_TAILS) \
                and not infl_chunk \
                and '固定搭配' not in c2_sub and '副词' not in c2_sub \
                and c2_lex not in ('固定搭配', '副词') \
                and not c2_whole_form \
                and not (simple and not c2_swallowed):
            flag(eid, 'C2', '词体「%s」以谓语尾结尾但未被切出谓语' % body)
        # ---- C3 助词误剥 / 词体不是完整词 ----
        # 短语块的词义在 phrase_gloss，这里逐个查它的成分；
        # 谓语块/终助词块/接续助词块不是名词词体，不参与词义检查。
        if c.get('phrase'):
            if not simple:
                check_phrase_components(eid, c.get('components'))
        elif body and not infl_chunk and not simple:
            # 词义查表只对引擎产物有意义；手写旧样例的动词块 gloss 是人工给的
            if ex.get('auto_generated') and not _c3_acceptable(body):
                g = M.gloss_of(body)
                if g is None:
                    flag(eid, 'C3', '词体「%s」查不到词义——可能是助词误剥或词表缺口' % body)
                elif g.get('partial') and not _partial_is_form_tail(g['partial']):
                    flag(eid, 'C3', '词体「%s」只靠前缀残配到「%s」——词体不是完整词' % (body, g['zh']))

        # ---- C4 汉字没有振假名 ----
        covered = ''.join(u['kanji'] for u in chunk_units(c) if u['type'] == 'ruby' and u['kana'])
        for k in KANJI.findall(body):
            if k not in covered:
                flag(eid, 'C4', '汉字「%s」（在「%s」中）没有振假名' % (k, body))

        # ---- C5 罗马音误读 ----
        rm = c.get('romaji') or ''
        for bad, why in ((r' ha\b', 'は 被读成 ha'), (r'^ha\b', 'は 被读成 ha'),
                         (r'deha', 'では 被读成 deha'), (r'\bhe\b', 'へ 被读成 he'),
                         (r'\bwo\b', 'を 被读成 wo'), (r'  ', '多余双空格')):
            if re.search(bad, rm):
                flag(eid, 'C5', '罗马音「%s」：%s' % (rm, why))
        # 长音符（ō/ā/ū）是正规赫本式转写，手写旧样例在用，不能算错
        # 数字要放行：教材数据层对数量词就是这么落罗马音的（300メートル → 300meetoru、
        # ２人 → 2nin），它们不是"没转写的假名/汉字"。
        if rm and not re.fullmatch(r"[0-9a-zA-Z~' .,!?\-Ā-ſ]+", rm):
            flag(eid, 'C5', '罗马音「%s」含非拉丁字符——可能汉字未被转写' % rm)

        # ---- C6 词义质量 ----
        gm = c.get('gloss_main') or ''
        if not gm and not simple:
            flag(eid, 'C6', '词「%s」词义为空' % body)
        # 注：「中国人→中国人」「猫→猫」这类词义与词同形是教材本来如此，不算错；
        # 「是（断定）」这类括号是形态说明而非体例残留（体例残留只出现在词义开头，
        # 已由 clean_gloss 剥掉）。故此处只查空词义。

        # ---- C7 下划线颜色与角色一致 ----
        uc = c.get('underline_color')
        if uc not in PALETTE:
            flag(eid, 'C7', '词「%s」下划线颜色非法：%s' % (body, uc))
        if part and uc != c.get('particle_color'):
            flag(eid, 'C7', '词「%s」下划线颜色(%s)与助词颜色(%s)不一致' % (body, uc, c.get('particle_color')))

    # ---- C8 直译行完整性 ----
    for cl in ex.get('literal_structure') or []:
        if not cl.get('tokens'):
            flag(eid, 'C8', '第%d小句直译行为空' % cl.get('clause'))
        for t in cl.get('tokens') or []:
            if not (t.get('text') or '').strip():
                flag(eid, 'C8', '直译行存在空 token')
            tgt = t.get('target_chunk')
            # zero_ga 是指向零主语红框的合法伪目标（diagram.js 特判）
            if tgt and tgt not in ids and tgt != 'zero_ga':
                flag(eid, 'C8', '直译 token「%s」指向不存在的块 %s' % (t.get('text'), tgt))
            if t.get('color') not in PALETTE:
                flag(eid, 'C8', '直译 token「%s」颜色非法 %s' % (t.get('text'), t.get('color')))

    # ---- C9 零主语推理与显隐规则 ----
    has_ga = any((c.get('particle') or '') == 'が' for c in chunks)
    has_topic = any((c.get('particle') or '') in ('は', 'も') for c in chunks)
    zs = ex.get('zero_subject')
    if has_ga and zs:
        flag(eid, 'C9', '已有显式 が 却仍标注零主语')
    if (not has_ga) and has_topic and not zs and not simple:
        flag(eid, 'C9', '有 は/も 话题且无显式 が，却缺少零主语标注')
    if zs:
        topic_ids = {c['id'] for c in chunks if (c.get('particle') or '') in ('は', 'も')}
        by_id = {c['id']: c for c in chunks}
        single_pred = sum(1 for c in chunks if looks_predicate(c)) == 1
        for t in zs.get('targets') or []:
            if t.get('id') not in ids:
                flag(eid, 'C9', '零主语箭头指向不存在的块 %s' % t.get('id'))
                continue
            if not (t.get('label') or '').strip():
                flag(eid, 'C12', '零主语箭头缺少标签文字')
            c = by_id[t['id']]
            p = c.get('particle') or ''
            # C12：主语箭头只有两种合法落点——
            #   ①「话题块」（は/も 把 が 吸收了，Ø が 与话题同指）
            #   ②「谓语块」（主语真的隐去了，箭头指向那个"谁做？"的谓语）
            # 钉在带格助词的论元块上，等于把"谁是主语"的箭头指向宾语或方向，
            # 这是 legacy 手写数据里真实出现过的错误（日本へ / 買い物を / 傘を）。
            if p in ('は', 'も') or looks_predicate(c):
                pass
            elif p in CASE_PARTICLES:
                flag(eid, 'C12', '零主语箭头钉在带格助词「%s」的论元块「%s」上，'
                                 '应指向话题块或谓语块' % (p, c.get('text')))
            elif p:
                flag(eid, 'C12', '零主语箭头钉在带「%s」的非谓语块「%s」上' % (p, c.get('text')))
            # 单谓语句里话题就是主语，箭头必须落在话题块（多小句句允许各小句自己的谓语）。
            # 例外（第19／22课）：话题是时间名词、谓语又不是名词谓语时，时间名词只是状语——
            #   昨日は とても 忙しかった／明日は 残業しなくても いいです。此时 Ø が 只能钉在谓语上，
            #   硬钉到时间名词上会教成"昨天是忙的主体"。
            if single_pred and topic_ids and t['id'] not in topic_ids \
                    and not time_topic_adverbial(chunks, topic_ids, c) \
                    and not quote_speaker_subject(chunks, target=c):
                flag(eid, 'C12', '单谓语句已有 は/も 话题，零主语箭头却指向「%s」而非话题块'
                                 % c.get('text'))

    # ---- C13 面向中文初学者的字段里不得残留英文 ----
    # 「1:1 复刻」只指视觉系统，不指文案语种。曾出现 particle_name 写成
    # 「格助词 (Direction)」、tooltip 写成「Zero Pronoun / it / I」的情况。
    zh_fields = []
    for c in chunks:
        for k in ('gloss_main', 'gloss_sub', 'particle_name', 'particle_desc'):
            if c.get(k):
                zh_fields.append(('chunks.%s' % k, c[k]))
    if zs:
        if zs.get('tooltip'):
            zh_fields.append(('zero_subject.tooltip', zs['tooltip']))
        for t in zs.get('targets') or []:
            if t.get('label'):
                zh_fields.append(('zero_subject.targets.label', t['label']))
    for cl in ex.get('literal_structure') or []:
        for t in cl.get('tokens') or []:
            if t.get('text'):
                zh_fields.append(('literal.text', t['text']))
    for k in ('natural_translation', 'lesson_title', 'tag'):
        if ex.get(k):
            zh_fields.append((k, ex[k]))
    # cognitive_note 不入检查：它是手写心法，为了讲"疑问句零语序代价"这类
    # 跨语言对比，会刻意引用英语原句（You are… / Are you…），那不是英文残留。
    for path, val in zh_fields:
        for w in LATIN_WORDS.findall(val):
            if w not in EN_WHITELIST:
                flag(eid, 'C13', '%s 残留英文「%s」：%s' % (path, w, val[:40]))

    # ---- C17 简单图不得夹带被裁掉的字段（课文口径：只要 词块＋助词框＋振假名） ----
    if simple:
        for c in chunks:
            if c.get('gloss_main') or c.get('gloss_sub') or c.get('lit_tokens'):
                flag(eid, 'C17', '简单图不该带词义／短语直译字段（%s）' % (c.get('text') or c.get('id')))
        for k in ('literal_structure', 'cognitive_note', 'zero_subject', 'tag', 'lesson_title'):
            if ex.get(k):
                flag(eid, 'C17', '简单图不该带 %s' % k)


    # ---- C5 句级罗马音 ----
    srm = ex.get('sentence_romaji') or ''
    if srm and not re.fullmatch(r"[0-9a-zA-Z~' .,!?\-Ā-ſ]+", srm):
        flag(eid, 'C5', '整句罗马音含非拉丁字符：%s' % srm)


def _covered_lessons():
    """已覆盖课次以 build_exemplars_auto.COVERED_LESSONS 为唯一来源，避免两处不一致。"""
    try:
        import build_exemplars_auto as BA
        return set(BA.COVERED_LESSONS)
    except Exception:
        return {1, 2, 3, 4}



def audit_coverage(exemplars, lessons):
    """C10：已覆盖课次的基本课文每句都要有透视图，且句面与教材一致。"""
    covered = _covered_lessons()
    have = {e['id'] for e in exemplars}
    for les in lessons:
        n = les['number']
        if n not in covered:
            continue
        for i, b4 in enumerate(les.get('basic4') or [], start=1):
            sid = 'l%d_b%d' % (n, i)
            if sid not in have:
                flag(sid, 'C10', '第%d课第%d句基本课文缺少透视图' % (n, i))
                continue
            # 句面比对以「修订后的教材正文」为准：教材数据里的注音/正文错字由
            # build_romaji.SOURCE_PATCHES 统一修订（lessons.json 保持只读），
            # 而引擎侧的 sentence_raw 是**渲染后**的句面（已去掉 ! 标记与 (かな) 注音），
            # 所以这一侧也要先渲染再比，否则正文订正会被误报成"与教材不一致"。
            want_clean = b4['jp_clean']
            try:
                import build_romaji as BR
                want_clean = M.render_text(BR.patch_raw(want_clean)[0]).get('clean') or want_clean
            except Exception:
                pass
            ex = next(e for e in exemplars if e['id'] == sid)
            want = re.sub(r'[\s。！？*]', '', want_clean)
            got = re.sub(r'[\s。！？*]', '', ex.get('sentence_raw') or '')
            if want != got:
                flag(sid, 'C10', '句面与教材不一致：教材=%s 引擎=%s' % (b4['jp_clean'], ex.get('sentence_raw')))

# ---- C14 数据层罗马音（全 48 课） ----
# 下面每一行对应一个真实修过的错误类别，期望值写死：
# 「改 A 坏 B」会立刻在这里现形，不需要等用户圈出来。
ROMAJI_CASES = (
    ('拗音词干（き／り／ぎ 必须带 y）', '* !京都(きょうと)の　!紅葉(もみじ)は　!有名(ゆうめい)です。',
     'kyouto no momiji wa yuumei desu.'),
    ('拗音词干', '!旅行(りょこう)は　とても　!楽(たの)しかったです。',
     'ryokou wa totemo tanoshikatta desu.'),
    ('拗音词干', '* !李(り)さんは　!図書館(としょかん)で　!勉強(べんきょう)します。',
     'ri san wa toshokan de benkyoushimasu.'),
    ('拗音词干', 'とても　おいしかったですよ。!特(とく)に　ギョーザは。',
     'totemo oishikatta desu yo. toku ni gyooza wa.'),
    ('拗音词干', 'きれいな　!人形(にんぎょう)を　!買(か)いました。',
     'kireina ningyou o kaimashita.'),
    ('促音（いっしょ 不是 itsho）',
     'ええ，!課長(かちょう)と　!一緒(いっしょ)に　!銀座(ぎんざ)へ　!行(い)きました。',
     'ee, kachou to isshoni ginza e ikimashita.'),
    ('纯假名词的尾字不当助词剥（とても／ほど）',
     '* !長島(ながしま)さんほど　!上手(じょうず)では　ありません。',
     'nagashima san hodo jouzu de wa arimasen.'),
    ('终助词独立成词', '* !先週(せんしゅう)　!休(やす)みましたか。', 'senshuu yasumimashita ka.'),
    ('终助词独立成词',
     '!吉田(よしだ)さんは　!来月(らいげつ)　!中国(ちゅうごく)へ　!行(い)きますか。',
     'yoshida san wa raigetsu chuugoku e ikimasu ka.'),
    ('注音里的全角空格占位', '!森(もり)さん，!引っ越(ひ　こ)しは!明日(あした)ですね　。',
     'mori san, hikkoshi wa ashita desu ne.'),
    ('存在动词与 〜ました 同形',
     '!李(り)さん，!何(なに)を　!買(か)いましたか。', 'ri san, nani o kaimashita ka.'),
    ('并列短语不被拍平', '* !部屋(へや)に　!机(つくえ)と　いすが　あります。',
     'heya ni tsukue to isu ga arimasu.'),
    # ---- 复合动词／形式名詞／促音的断词依据（第 9–14 课扩课时一并做）----
    ('形式名詞前断词（見ることが → miru koto）',
     '!中国(ちゅうごく)の　!獅子舞(ししまい)を　!見(み)ることが　できますよ。',
     'chuugoku no shishimai o miru koto ga dekimasu yo.'),
    ('形式名詞 はず 不被 は＋ず 切开',
     '* !会議(かいぎ)は５!時(じ)までですから，もうすぐ!終(お)わるはずです。',
     'kaigi wa 5 ji made desu kara, mousugu owaru hazu desu.'),
    ('促音跨语块（1杯＝いっぱい，不是 it pai）',
     '!生(なま)ビールが　!1(いっ)!杯(ぱい)!300(さんびゃく)!円(えん)ですか。',
     'namabiiru ga ippai sanbyaku en desu ka.'),
    ('促音便＋連濁（一本 いっほん → ippon）',
     '!焼(や)き!鳥(とり)は　!一(いっ)!本(ほん)　!150(ひゃくごじゅう)!円(えん)ぐらいですよ。',
     'yaki tori wa ippon hyakugojuu engurai desu yo.'),
    # ---- 第13～14课：数量词与て形 ----
    ('Vない形不被切碎（行かない → ikanai）',
     '!明日(あした)　ボーリングに　!行(い)かない？',
     'ashita booringu ni ikanai?'),
    ('て形＋てから（聞いてから → kiite kara）',
     '!李(り)さんは　!毎晩(まいばん)　ラジオを　!聞(き)いてから　!寝(ね)ます。',
     'ri san wa maiban rajio o kiite kara nemasu.'),
    ('行く 的て形例外（いって → itte）',
     '* !昨日(きのう)　デパートへ　いって　!買(か)い!物(もの)しました。',
     'kinou depaato e itte kaimonoshimashita.'),
    ('数量词的促音便（一週間 → isshuukan）',
     '* !李(り)さんは　!一週間(いっしゅうかん)に　!二回(にかい)　プールへ　!行(い)きます。',
     'ri san wa isshuukan ni nikai puuru e ikimasu.'),
)


# ---- C16 注音合法性（教材数据层面；这一项会拦构建） ----
# 小写假名只能跟在拗音／外来语音的特定假名后面（きゃ／シェ／ファ／ティ／ウィ…），
# 孤立出现一定是错字：行(ぃ)きました、上海(シャンハィ) 都是这一类（本轮人工找出来的）。
# 另一条是同词注音里平假名与片假名混用（北京(ぺキン)）。
# 有了这条检查，同一类错字以后会自己现形，不必再靠人翻教材。
_SMALL_KANA = set('ぁぃぅぇぉゃゅょゎァィゥェォャュョヮ')
_SMALL_LEAD = set('きしちにひみりぎじびぴふてでうゔくすつ'
                  'キシチニヒミリギジビピフテデウヴクスツヰヱ')


def audit_kana_legality(lessons):
    """C16：注音里不得出现孤立的小写假名，也不得平／片假名混用。
    检查的是**套过 SOURCE_PATCHES 之后**的句面——已修订的错字不再报，
    剩下的才是需要人工判读的新错误。"""
    try:
        import build_romaji as B
    except Exception:                              # pragma: no cover
        B = None
    for les in lessons:
        for raw in _iter_raw_sentences(les):
            if not raw:
                continue
            if B is not None:
                raw = B.patch_raw(raw)[0]
            for surf, tail, read in _ann_fragments(raw):
                # ① 孤立小写假名：行(ぃ)／上海(シャンハィ) 这一类
                for k, ch in enumerate(read):
                    if ch in _SMALL_KANA and (k == 0 or read[k - 1] not in _SMALL_LEAD):
                        flag('reading', 'C16', '注音「%s」（%s）里的「%s」是孤立小写假名——疑教材错字'
                             % (read, surf, ch))
                # ② 首字假名种类与其余不一致：ぺキン（应为 ペキン）✓ 报
                #    ペキンししゃ（片假名音节＋平假名送假名）是合法注音 ✗ 不报
                hira = [c for c in read if 'ぁ' <= c <= 'ゖ']
                kata = [c for c in read if 'ァ' <= c <= 'ヶ']
                if hira and kata and len(read) > 1:
                    first = read[0]
                    if ('ぁ' <= first <= 'ゖ' and len(hira) == 1) \
                            or ('ァ' <= first <= 'ヶ' and len(kata) == 1):
                        flag('reading', 'C16', '注音「%s」（%s）首字假名种类与其余不一致——疑教材错字'
                             % (read, surf))


def audit_romaji_layer(lessons):
    """C14：回归用例表 + 数据层自检 + 「data/romaji.json 与 lessons.json 同步」。"""
    for label, raw, want in ROMAJI_CASES:
        got = M.analyze_sentence(raw)['romaji']
        if got != want:
            flag('romaji', 'C14', '%s 回归用例失败：「%s」期望「%s」实得「%s」'
                 % (label, raw, want, got))
    try:
        import build_romaji as B
    except Exception as exc:                       # pragma: no cover
        flag('romaji', 'C14', '无法导入 build_romaji：%r' % (exc,))
        return
    data = B.build(lessons)
    for p in B.self_check(data, lessons):
        flag('romaji', 'C14', p)
    path = os.path.join(HERE, 'data', 'romaji.json')
    if not os.path.exists(path):
        flag('romaji', 'C14', '缺少 data/romaji.json（先跑 python build_romaji.py）')
        return
    with io.open(path, encoding='utf-8') as f:
        on_disk = json.load(f)
    for key in ('sentences', 'words', 'titles'):
        if on_disk.get(key) != data[key]:
            flag('romaji', 'C14', 'data/romaji.json 的 %s 与 lessons.json 不同步，'
                                  '请重新运行 python build_romaji.py' % key)


# ---- C15 教材内部注音一致性（只报不拦） ----
# 同一注音片段（汉字串＋紧跟的送假名）在全书出现不同注音时，多数是合法多音
# （中 ちゅう／なか、人 ひと／じん／にん、時 じ／とき、明日 あした／あす／みょうにち…），
# 少数是真错字（晴(ほ)れ、帰(かぇ)り、行(ぃ)きました、一杯(はい)）。
# 判读权在人，所以这一项**只报不拦**（不写 problems、不影响 exit code）：
# 机器把候选摆到桌面上，并自动归类——
#   ① LEGAL_READING 白名单里的合法多音
#   ② SOURCE_PATCHES 已经修订过的错字（套一遍补丁，看这个片段的注音是否归一）
# 剩下的逐条列出（附出处与原文），这才是需要人工判读的部分。
# 上一轮只跑在 scratch 里的扫描脚本，这一轮变成常驻报告项；
# 它当场找出两处上一轮漏掉的错字（第10课 行(ぃ)きました、第13课 一杯(はい)）。
LEGAL_READING = {
    '中': ('ちゅう', 'なか'),
    '人': ('ひと', 'じん', 'にん'),
    '何': ('なに', 'なん'),
    '時': ('じ', 'とき'),
    '日': ('ひ', 'び', 'にち', 'か'),        # 日(ひ)／誕生(び)日／日(にち)曜日／３(か)日
    '度': ('ど', 'たび'),
    '私': ('わたし', 'わたくし'),
    '市場': ('いちば', 'しじょう'),
    '明日': ('あした', 'あす', 'みょうにち'),
    '昨日': ('きのう', 'さくじつ'),
    # ---- 下面这一批是本次扫描逐个判读后收录的「同一汉字在不同词里本来就不同音」----

    # 判据：两边都是日语里真实存在的读法，且各自出现多次（教材自身混用的另注）。
    '三': ('さん', 'みっ'),
    '上': ('うえ', 'あ', 'じょう'),
    '下': ('お', 'くだ', 'した', 'げ'),
    '入': ('はい', 'い', 'にゅう'),
    '出': ('で', 'だ', 'しゅつ'),
    '分': ('わ', 'ふん', 'ぶん'),
    '周': ('まわ', 'しゅう'),
    '場': ('ば', 'じょう'),
    '変': ('か', 'へん'),
    '少': ('すこ', 'すく'),
    '後': ('あと', 'ご', 'うし'),
    '急': ('いそ', 'きゅう'),
    '新': ('あたら', 'しん'),
    '方': ('かた', 'ほう'),
    '日本': ('にほん', 'にっぽん'),          # 两种读法都成立，教材自身混用
    '日本人': ('にほんじん', 'にっぽんじん'),
    '書': ('か', 'しょ'),
    '来': ('き', 'く', 'こ'),
    '杯': ('ぱい', 'ばい'),
    '母': ('はは', 'かあ'),
    '消': ('け', 'き'),
    '済': ('す', 'すみ'),
    '熱': ('あつ', 'ねつ'),
    '着': ('つ', 'き'),
    '空': ('から', 'そら'),
    '紅葉': ('もみじ', 'こうよう'),          # 和语／汉语两种读法都成立
    '行': ('い', 'ゆ'),
    '話': ('はな', 'はなし'),
    '通': ('とお', 'かよ', 'つう'),
    '遅': ('おそ', 'おく'),
    '量': ('りょう', 'はか'),
    '長': ('ちょう', 'なが'),
    '開': ('あ', 'ひら'),
    '集': ('あつ', 'しゅう'),
    '１': ('いっ', 'ひと'),
}


def _ann_fragments(raw):
    """一句 jp_raw → [(汉字串, 紧跟的送假名, 注音)]（同一语块之内）。"""
    out = []
    for seg in M.group_tokens(M.tokenize_raw(raw)):
        if seg['kind'] == 'punct':
            continue
        parts = seg.get('parts') or []
        for k, p in enumerate(parts):
            if not p.get('ann'):
                continue
            tail = ''
            for q in parts[k + 1:]:
                if q.get('ann'):
                    break
                tail += q['surf']
            out.append((p['surf'], tail, p['read']))
    return out


def _iter_raw_sentences(lesson):
    for s in lesson.get('basic4') or []:
        yield s.get('jp_raw') or ''
    for s in lesson.get('basicc') or []:
        yield s.get('jp_raw') or ''
    for sec in lesson.get('context_sections') or []:
        for s in sec:
            if s.get('type') == 'dialogue':
                yield s.get('jp_raw') or ''


def report_reading_consistency(lessons):
    """C15：返回打印用的报告行（只报不拦）。"""
    try:
        import build_romaji as B
    except Exception:                              # pragma: no cover
        B = None
    # 按「汉字串」分组（不把送假名算进键）：晴(ほ)れでした／晴(は)れだそうですよ
    # 这种错字对的送假名往往不同，算进键会漏掉——而合法多音由 LEGAL_READING 兜住。
    groups = {}
    for les in lessons:
        for raw in _iter_raw_sentences(les):
            if not raw:
                continue
            for surf, tail, read in _ann_fragments(raw):
                groups.setdefault(surf, {}).setdefault(read, []).append(
                    (les['number'], raw, tail))

    legal = patched = todo = 0
    detail = []
    for surf, readings in sorted(groups.items()):
        if len(readings) < 2:
            continue
        # ① 已经被 SOURCE_PATCHES 修订掉的注音：套一遍补丁，看它是否消失
        fixed = set()
        if B is not None:
            for read, occ in readings.items():
                num, raw, _tail = occ[0]
                patched_raw, changed = B.patch_raw(raw)
                if not changed:
                    continue
                after = {r for s, _t, r in _ann_fragments(patched_raw) if s == surf}
                if read not in after:
                    fixed.add(read)
        remaining = {r for r in readings if r not in fixed}
        allowed = set(LEGAL_READING.get(surf, ()))
        # ② 剩下的注音都是白名单里的合法异读（或只剩一种）→ 不当候选
        if len(remaining) < 2 or (allowed and remaining <= allowed):
            if fixed:
                patched += 1
            else:
                legal += 1
            continue
        todo += 1
        detail.append('    %s：%s' % (
            surf,
            ' / '.join('%s×%d' % (r, len(v)) for r, v in sorted(readings.items(), key=lambda kv: -len(kv[1])))))
        for read, occ in sorted(readings.items(), key=lambda kv: (-len(kv[1]), kv[0])):
            num, raw, _tail = occ[0]
            mark = '［已由 SOURCE_PATCHES 修订］' if read in fixed else ''
            detail.append('        - %s%s（第%d课）  %s'
                          % (read, mark, num, raw.strip()[:68]))

    lines = ['【C15 教材注音一致性（同一汉字多种注音，只报不拦）】'
             '合法多音 %d 组 / 已由 SOURCE_PATCHES 修订 %d 组 / 待人工判读 %d 组'
             % (legal, patched, todo)]
    if todo:
        lines.append('  ！！待判读（可能是教材错字或合法异读：人工确认后进 SOURCE_PATCHES 或 LEGAL_READING）：')
        lines.extend(detail)
    else:
        lines.append('  待判读为空：剩下的多音都是合法异读，或已由 SOURCE_PATCHES 修订。')
    audit_kana_legality(lessons)
    return lines


def dump(exemplars):
    for e in exemplars:
        print('=' * 70)
        print('%s | %s' % (e['id'], e.get('sentence_raw')))
        print('  romaji: %s' % e.get('sentence_romaji'))
        zs = e.get('zero_subject')
        print('  zero  : %s' % ('-' if not zs else 'Ø が -> ' + ', '.join(t['label'] for t in zs['targets'])))
        for c in e.get('chunks') or []:
            units = chunk_units(c)
            vis = ''.join(('[%s]' % u['particle']) if u['type'] == 'box' else u['kanji'] for u in units)
            print('    %-16s part=%-3s(%-6s) underline=%-7s gloss=%-14s sub=%s'
                  % (vis, c.get('particle') or '-', c.get('particle_color'),
                     c.get('underline_color'), c.get('gloss_main'), c.get('gloss_sub', '')))
        for cl in e.get('literal_structure') or []:
            print('    LIT%d: %s' % (cl['clause'], ' '.join(t['text'] for t in cl['tokens'])))
        print('    中文: %s' % e.get('natural_translation'))


def main():
    with io.open(EXEMPLARS, encoding='utf-8') as f:
        exemplars = json.load(f)
    with io.open(LESSONS, encoding='utf-8') as f:
        lessons = json.load(f)

    # --prune-simple：把"有缺陷的课文简单条目"先从数据里摘掉再报告。
    # 口径与审计本身一致（C1/C2/C4/C5/C7/C17…），所以这批条目一旦被引擎修好，
    # 下次构建就会自动回到数据里——不需要人工维护黑名单。
    if '--prune-simple' in sys.argv:
        bad_ids = set()
        for e in exemplars:
            if not e.get('simple'):
                continue
            problems[:] = []
            audit(e)
            if problems:
                bad_ids.add(e['id'])
        if bad_ids:
            keep = [e for e in exemplars if e['id'] not in bad_ids]
            with io.open(EXEMPLARS, 'w', encoding='utf-8') as f:
                json.dump(keep, f, ensure_ascii=False, indent=2)
            print('先摘掉 %d 条未达标的课文简单条目（引擎修好后会自动回来）：' % len(bad_ids))
            print('   ' + ', '.join(sorted(bad_ids)[:60])
                  + (' …' if len(bad_ids) > 60 else ''))
            exemplars = keep
        else:
            print('课文简单条目全部达标，无需摘除。')

    problems[:] = []
    for e in exemplars:
        audit(e)
    audit_coverage(exemplars, lessons)
    audit_romaji_layer(lessons)
    # C15 只报不拦：候选摆出来给人判读，不进 problems、不影响 exit code
    reading_report = report_reading_consistency(lessons)

    if '--dump' in sys.argv:
        dump(exemplars)
        print()

    if problems:
        by_code = {}
        for eid, code, msg in problems:
            by_code.setdefault(code, []).append((eid, msg))
        print('!! 审计发现 %d 个问题：' % len(problems))
        for code in sorted(by_code):
            print('  [%s] %d 处' % (code, len(by_code[code])))
            for eid, msg in by_code[code][:25]:
                print('      %s: %s' % (eid, msg))
        print()
        for line in reading_report:
            print(line)
        raise SystemExit(1)
    for line in reading_report:
        print(line)
    print('审计通过：C1～C14 全类别零问题（%d 条透视图 + 全 48 课罗马音数据层）；'
          'C15 为只读报告（见上）' % len(exemplars))


if __name__ == '__main__':
    main()
