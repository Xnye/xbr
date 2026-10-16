import json
import os

exemplars = [
    {
        "id": "screenshot_showcase",
        "lesson": 11,
        "is_featured": True,
        "tag": "视频1:1原型",
        "lesson_title": "经典视频原型：原因从句与复合动作",
        "sentence_raw": "今日は雨だから傘を持っていく",
        "zero_subject": {
            "symbol": "Ø",
            "particle": "が",
            "tooltip": "【Ø が】隐性主语（零代词 Zero Pronoun）。日语每个谓语（动词/形容词/名词+断定）在深层语法中都必须由「が」驱动。当语境明确时，主语通常被省略（记为 Ø）。此处前句隐去「天气/自然(it) が 雨だ」，后句隐去说话人「我(I) が 傘を持っていく」。初学者常以为日语没有主语，实则主语一直在后台运转！",
            "targets": [
                {"id": "chunk_ame", "label": "it (天气/自然)"},
                {"id": "chunk_kasa", "label": "I (说话人/我)"}
            ]
        },
        "chunks": [
            {
                "id": "chunk_kyou",
                "text": "今日",
                "ruby": "きょう",
                "romaji": "kyō",
                "particle": "は",
                "particle_color": "blue",
                "particle_name": "提示助词 (Topic)",
                "particle_desc": "【は】设定谈话背景舞台（“至于今天呢 / As for today”）。它不是主格，而是聚光灯，圈定话题范围。",
                "underline_color": "blue",
                "underline_span": "full",
                "gloss_main": "today",
                "gloss_sub": ""
            },
            {
                "id": "chunk_ame",
                "text": "雨だ",
                "ruby_parts": [{"kanji": "雨", "kana": "あめ"}, {"kanji": "だ", "kana": ""}],
                "romaji": "ame da",
                "particle": "から",
                "particle_color": "cyan",
                "particle_name": "接续助词 (Reason)",
                "particle_desc": "【から】原因理由小句。“因为……”。前接简体谓语「雨だ」，构成状语从句。",
                "underline_color": "cyan",
                "underline_span": "full",
                "gloss_main": "rain is",
                "gloss_sub": "(copula)"
            },
            {
                "id": "chunk_kasa",
                "text": "傘",
                "ruby": "かさ",
                "romaji": "kasa",
                "particle": "を",
                "particle_color": "orange",
                "particle_name": "宾格助词 (Object)",
                "particle_desc": "【を】及物动词的作用对象。标记「傘」作为带走的实体宾语。",
                "underline_color": "orange",
                "underline_span": "full",
                "gloss_main": "umbrella",
                "gloss_sub": ""
            },
            {
                "id": "chunk_motte",
                "text": "持っ",
                "ruby": "も",
                "romaji": "motte",
                "suffix": "て",
                "particle": "",
                "underline_color": "none",
                "gloss_main": "bring",
                "gloss_sub": "(て-form of 持つ)"
            },
            {
                "id": "chunk_iku",
                "text": "いく",
                "ruby": "",
                "romaji": "iku",
                "particle": "",
                "underline_color": "none",
                "gloss_main": "go",
                "gloss_sub": ""
            }
        ],
        "literal_structure": [
            {
                "clause": 1,
                "tokens": [
                    {"text": "because", "color": "cyan", "underline": True, "target_chunk": "chunk_ame"},
                    {"text": "as for", "color": "blue", "underline": True, "target_chunk": "chunk_kyou"},
                    {"text": "today,", "color": "normal", "underline": False},
                    {"text": "(it)", "color": "red", "underline": True, "target_chunk": "zero_ga"},
                    {"text": "is rain,", "color": "normal", "underline": False}
                ]
            },
            {
                "clause": 2,
                "tokens": [
                    {"text": "(i)", "color": "red", "underline": True, "target_chunk": "zero_ga"},
                    {"text": "bring", "color": "normal", "underline": False},
                    {"text": "umbrella", "color": "orange", "underline": True, "target_chunk": "chunk_kasa"},
                    {"text": "and go", "color": "normal", "underline": False}
                ]
            }
        ],
        "natural_translation": "所以，因为今天下雨，我要带上伞出门。",
        "cognitive_note": "【核心语法心法】日语句子由句尾谓语逆向驱动：①「雨だ」需要主语，深层语境默认是天气 (Ø が)；②「持っていく」需要主语，深层语境默认是说话人 (Ø が)；③「今日は」将整件事置于“今天”这个舞台上；④「から」负责把两个小句因果锁定。"
    },
    {
        "id": "l1_b1",
        "lesson": 1,
        "is_featured": False,
        "tag": "第1课 核心判断句",
        "lesson_title": "第1课：李さんは中国人です",
        "sentence_raw": "李さんは中国人です",
        "zero_subject": {
            "symbol": "Ø",
            "particle": "が",
            "tooltip": "【Ø が】隐性格助词：在判断句「名詞＋です」中，「中国人です」是谓语，“谁是中国人”由隐性主语 Ø が 承担。它指向话题圈定的人物「李さん」。",
            "targets": [
                {"id": "chunk_chukoku", "label": "she (小李)"}
            ]
        },
        "chunks": [
            {
                "id": "chunk_ri",
                "text": "李さん",
                "ruby_parts": [{"kanji": "李", "kana": "り"}, {"kanji": "さん", "kana": ""}],
                "romaji": "ri san",
                "particle": "は",
                "particle_color": "blue",
                "particle_name": "提示助词 (Topic)",
                "particle_desc": "【は】提示全句主题：“关于小李 / 提到小李”。将小李推向对话聚光灯。",
                "underline_color": "blue",
                "underline_span": "full",
                "gloss_main": "Ms. Li",
                "gloss_sub": "(topic)"
            },
            {
                "id": "chunk_chukoku",
                "text": "中国人",
                "ruby": "ちゅうごくじん",
                "romaji": "chūgokujin",
                "particle": "です",
                "particle_color": "green",
                "particle_name": "断定助动词 (Polite Copula)",
                "particle_desc": "【です】礼貌体断定动词。“是……”。给名词赋予谓语功能并体现敬意。",
                "underline_color": "green",
                "underline_span": "full",
                "gloss_main": "Chinese",
                "gloss_sub": "is (polite copula)"
            }
        ],
        "literal_structure": [
            {
                "clause": 1,
                "tokens": [
                    {"text": "as for", "color": "blue", "underline": True, "target_chunk": "chunk_ri"},
                    {"text": "Ms. Li,", "color": "normal", "underline": False},
                    {"text": "(she)", "color": "red", "underline": True, "target_chunk": "zero_ga"},
                    {"text": "is", "color": "green", "underline": True, "target_chunk": "chunk_chukoku"},
                    {"text": "Chinese.", "color": "normal", "underline": False}
                ]
            }
        ],
        "natural_translation": "小李是中国人。",
        "cognitive_note": "【新手解惑】不要把「は」死记成中文的“是”。「は」是“关于/至于”，而「です」才是断定词“是”。全句结构是：关于小李（舞台），[她] 是中国人（主谓事实）。"
    },
    {
        "id": "l1_b2",
        "lesson": 1,
        "is_featured": False,
        "tag": "第1课 否定判断句",
        "lesson_title": "第1课：森さんは学生ではありません",
        "sentence_raw": "森さんは学生ではありません",
        "zero_subject": {
            "symbol": "Ø",
            "particle": "が",
            "tooltip": "【Ø が】隐性主语：指代森先生。否定谓语「学生ではありません」的深层主体也是 (Ø が)。",
            "targets": [
                {"id": "chunk_gakusei", "label": "he (森先生)"}
            ]
        },
        "chunks": [
            {
                "id": "chunk_mori",
                "text": "森さん",
                "ruby_parts": [{"kanji": "森", "kana": "もり"}, {"kanji": "さん", "kana": ""}],
                "romaji": "mori san",
                "particle": "は",
                "particle_color": "blue",
                "particle_name": "提示助词 (Topic)",
                "particle_desc": "【は】提示话题：“至于森先生”。",
                "underline_color": "blue",
                "underline_span": "full",
                "gloss_main": "Mr. Mori",
                "gloss_sub": "(topic)"
            },
            {
                "id": "chunk_gakusei",
                "text": "学生",
                "ruby": "がくせい",
                "romaji": "gakusei",
                "particle": "では ありません",
                "particle_color": "purple",
                "particle_name": "否定断定 (Negative Copula)",
                "particle_desc": "【ではありません】「です」的否定敬体形式。口语中「では」常缩读为「じゃ」。",
                "underline_color": "purple",
                "underline_span": "full",
                "gloss_main": "student",
                "gloss_sub": "is not"
            }
        ],
        "literal_structure": [
            {
                "clause": 1,
                "tokens": [
                    {"text": "as for", "color": "blue", "underline": True, "target_chunk": "chunk_mori"},
                    {"text": "Mr. Mori,", "color": "normal", "underline": False},
                    {"text": "(he)", "color": "red", "underline": True, "target_chunk": "zero_ga"},
                    {"text": "is not", "color": "purple", "underline": True, "target_chunk": "chunk_gakusei"},
                    {"text": "a student.", "color": "normal", "underline": False}
                ]
            }
        ],
        "natural_translation": "森先生不是学生。",
        "cognitive_note": "【否定逻辑】日语断定否定词「ではありません」内部也暗含「は」：由「で（接续）＋ は（强调对比）＋ ありません（不存在/不是）」构成。"
    },
    {
        "id": "l4_b1",
        "lesson": 4,
        "is_featured": False,
        "tag": "第4课 存在句（物体）",
        "lesson_title": "第4课：部屋に机があります",
        "sentence_raw": "部屋に机があります",
        "zero_subject": None,  # が is explicit here!
        "chunks": [
            {
                "id": "chunk_heya",
                "text": "部屋",
                "ruby": "へや",
                "romaji": "heya",
                "particle": "に",
                "particle_color": "purple",
                "particle_name": "格助词 (Location)",
                "particle_desc": "【に】标记静止存在的场所坐标点。“在……”。",
                "underline_color": "purple",
                "underline_span": "full",
                "gloss_main": "room",
                "gloss_sub": "(in / at)"
            },
            {
                "id": "chunk_tsukue",
                "text": "机",
                "ruby": "つくえ",
                "romaji": "tsukue",
                "particle": "が",
                "particle_color": "red",
                "particle_name": "格助词 (Explicit Subject)",
                "particle_desc": "【が】显性主格！此处主语不再是隐性的 Ø，而是明确的「机」作为存在主体！",
                "underline_color": "red",
                "underline_span": "full",
                "gloss_main": "desk",
                "gloss_sub": "(subject)"
            },
            {
                "id": "chunk_arimasu",
                "text": "あります",
                "ruby": "",
                "romaji": "arimasu",
                "particle": "",
                "underline_color": "none",
                "gloss_main": "exists",
                "gloss_sub": "(inanimate)"
            }
        ],
        "literal_structure": [
            {
                "clause": 1,
                "tokens": [
                    {"text": "in", "color": "purple", "underline": True, "target_chunk": "chunk_heya"},
                    {"text": "room,", "color": "normal", "underline": False},
                    {"text": "a desk", "color": "red", "underline": True, "target_chunk": "chunk_tsukue"},
                    {"text": "exists.", "color": "normal", "underline": False}
                ]
            }
        ],
        "natural_translation": "房间里有桌子。",
        "cognitive_note": "【显性「が」的震撼】在存在句「场所 に 事物 が あります」中，「が」终于登场了！这完美印证了底层原理：有生命/无生命的存在动词，直接受「が」驱动。「に」负责锚定空间坐标。"
    },
    {
        "id": "l4_b3",
        "lesson": 4,
        "is_featured": False,
        "tag": "第4课 存在句（人物主题）",
        "lesson_title": "第4课：小野さんは事務所にいます",
        "sentence_raw": "小野さんは事務所にいます",
        "zero_subject": {
            "symbol": "Ø",
            "particle": "が",
            "tooltip": "【Ø が】隐性主语：在「小野さんは事務所にいます」中，小野被提至句首作为舞台主题 (は)，而「います」前省略了 (小野さんが)。",
            "targets": [
                {"id": "chunk_jimusho", "label": "she (小野)"}
            ]
        },
        "chunks": [
            {
                "id": "chunk_ono",
                "text": "小野さん",
                "ruby_parts": [{"kanji": "小野", "kana": "おの"}, {"kanji": "さん", "kana": ""}],
                "romaji": "ono san",
                "particle": "は",
                "particle_color": "blue",
                "particle_name": "提示助词 (Topic)",
                "particle_desc": "【は】提示话题：“小野女士在哪里呢？”",
                "underline_color": "blue",
                "underline_span": "full",
                "gloss_main": "Ms. Ono",
                "gloss_sub": "(topic)"
            },
            {
                "id": "chunk_jimusho",
                "text": "事務所",
                "ruby": "じむしょ",
                "romaji": "jimusho",
                "particle": "に",
                "particle_color": "purple",
                "particle_name": "格助词 (Location)",
                "particle_desc": "【に】存在场所。“在事务所”。",
                "underline_color": "purple",
                "underline_span": "full",
                "gloss_main": "office",
                "gloss_sub": "(in / at)"
            },
            {
                "id": "chunk_imasu",
                "text": "います",
                "ruby": "",
                "romaji": "imasu",
                "particle": "",
                "underline_color": "none",
                "gloss_main": "is (present)",
                "gloss_sub": "(animate)"
            }
        ],
        "literal_structure": [
            {
                "clause": 1,
                "tokens": [
                    {"text": "as for", "color": "blue", "underline": True, "target_chunk": "chunk_ono"},
                    {"text": "Ms. Ono,", "color": "normal", "underline": False},
                    {"text": "(she)", "color": "red", "underline": True, "target_chunk": "zero_ga"},
                    {"text": "in", "color": "purple", "underline": True, "target_chunk": "chunk_jimusho"},
                    {"text": "the office is.", "color": "normal", "underline": False}
                ]
            }
        ],
        "natural_translation": "小野女士在事务所。",
        "cognitive_note": "【います vs あります】人或动物（有生命）的存在用「います」，植物或非生命体用「あります」。对比上一句：当以人物为主题时，人物用「は」放句首，空间「に」在中间。"
    },
    {
        "id": "l6_b1",
        "lesson": 6,
        "is_featured": False,
        "tag": "第6课 移动动词与伴随者",
        "lesson_title": "第6课：李さんは森さんと日本へ行きました",
        "sentence_raw": "李さんは森さんと日本へ行きました",
        "zero_subject": {
            "symbol": "Ø",
            "particle": "が",
            "tooltip": "【Ø が】隐性主语：真正执行移动动作「行きました」的是 (李さんが)。",
            "targets": [
                {"id": "chunk_nihon", "label": "she (小李)"}
            ]
        },
        "chunks": [
            {
                "id": "chunk_ri_6",
                "text": "李さん",
                "ruby_parts": [{"kanji": "李", "kana": "り"}, {"kanji": "さん", "kana": ""}],
                "romaji": "ri san",
                "particle": "は",
                "particle_color": "blue",
                "particle_name": "提示助词 (Topic)",
                "particle_desc": "【は】提示话题主体：小李。",
                "underline_color": "blue",
                "underline_span": "full",
                "gloss_main": "Ms. Li",
                "gloss_sub": "(topic)"
            },
            {
                "id": "chunk_mori_6",
                "text": "森さん",
                "ruby_parts": [{"kanji": "森", "kana": "もり"}, {"kanji": "さん", "kana": ""}],
                "romaji": "mori san",
                "particle": "と",
                "particle_color": "yellow",
                "particle_name": "格助词 (Companion)",
                "particle_desc": "【と】伴随者助词。“和森先生一起”。",
                "underline_color": "yellow",
                "underline_span": "full",
                "gloss_main": "Mr. Mori",
                "gloss_sub": "(with)"
            },
            {
                "id": "chunk_nihon",
                "text": "日本",
                "ruby": "にほん",
                "romaji": "nihon",
                "particle": "へ",
                "particle_color": "magenta",
                "particle_name": "格助词 (Direction)",
                "particle_desc": "【へ】移动的方向/目的地助词（读作 e）。“往/去日本”。",
                "underline_color": "magenta",
                "underline_span": "full",
                "gloss_main": "Japan",
                "gloss_sub": "(towards)"
            },
            {
                "id": "chunk_ikimashita",
                "text": "行きました",
                "ruby_parts": [{"kanji": "行", "kana": "い"}, {"kanji": "きました", "kana": ""}],
                "romaji": "ikimashita",
                "particle": "",
                "underline_color": "none",
                "gloss_main": "went",
                "gloss_sub": "(past)"
            }
        ],
        "literal_structure": [
            {
                "clause": 1,
                "tokens": [
                    {"text": "as for", "color": "blue", "underline": True, "target_chunk": "chunk_ri_6"},
                    {"text": "Ms. Li,", "color": "normal", "underline": False},
                    {"text": "with", "color": "yellow", "underline": True, "target_chunk": "chunk_mori_6"},
                    {"text": "Mr. Mori,", "color": "normal", "underline": False},
                    {"text": "towards", "color": "magenta", "underline": True, "target_chunk": "chunk_nihon"},
                    {"text": "Japan,", "color": "normal", "underline": False},
                    {"text": "(she)", "color": "red", "underline": True, "target_chunk": "zero_ga"},
                    {"text": "went.", "color": "normal", "underline": False}
                ]
            }
        ],
        "natural_translation": "小李和森先生一起去了日本。",
        "cognitive_note": "【助词各司其职】你看！日语助词就像给名词贴上的功能便利贴：贴上「と」就是伙伴，贴上「へ」就是方向，贴上「は」就是舞台大背景，最后动词「行きました」收尾。条理极其清晰！"
    },
    {
        "id": "l14_b1",
        "lesson": 14,
        "is_featured": False,
        "tag": "第14课 动词て形相继发生",
        "lesson_title": "第14课：昨日デパートへ行って、買い物をしました",
        "sentence_raw": "昨日デパートへ行って、買い物をしました",
        "zero_subject": {
            "symbol": "Ø",
            "particle": "が",
            "tooltip": "【Ø が】双重动作隐性主语：动作执行人都是「我 (Ø が)」。",
            "targets": [
                {"id": "chunk_itte", "label": "I (我)"},
                {"id": "chunk_kaimono", "label": "I (我)"}
            ]
        },
        "chunks": [
            {
                "id": "chunk_kinou",
                "text": "昨日",
                "ruby": "きのう",
                "romaji": "kinō",
                "particle": "",
                "underline_color": "none",
                "gloss_main": "yesterday",
                "gloss_sub": ""
            },
            {
                "id": "chunk_depaato",
                "text": "デパート",
                "ruby": "",
                "romaji": "depāto",
                "particle": "へ",
                "particle_color": "magenta",
                "particle_name": "格助词 (Direction)",
                "particle_desc": "【へ】移动方向。“去百货商场”。",
                "underline_color": "magenta",
                "underline_span": "full",
                "gloss_main": "department store",
                "gloss_sub": "(towards)"
            },
            {
                "id": "chunk_itte",
                "text": "行って",
                "ruby_parts": [{"kanji": "行", "kana": "い"}, {"kanji": "って", "kana": ""}],
                "romaji": "itte",
                "particle": "、",
                "particle_color": "cyan",
                "particle_name": "相继接续 (Te-form)",
                "particle_desc": "【て形】动词的万能连接符！表示前一个动作先发生，随后紧接着进行下一动作。",
                "underline_color": "cyan",
                "underline_span": "full",
                "gloss_main": "go and",
                "gloss_sub": "(て-form)"
            },
            {
                "id": "chunk_kaimono",
                "text": "買い物",
                "ruby": "かいもの",
                "romaji": "kaimono",
                "particle": "を",
                "particle_color": "orange",
                "particle_name": "宾格助词 (Object)",
                "particle_desc": "【を】及物动作对象。“购物”。",
                "underline_color": "orange",
                "underline_span": "full",
                "gloss_main": "shopping",
                "gloss_sub": ""
            },
            {
                "id": "chunk_shimashita",
                "text": "しました",
                "ruby": "",
                "romaji": "shimashita",
                "particle": "",
                "underline_color": "none",
                "gloss_main": "did",
                "gloss_sub": "(past)"
            }
        ],
        "literal_structure": [
            {
                "clause": 1,
                "tokens": [
                    {"text": "yesterday", "color": "normal", "underline": False},
                    {"text": "to", "color": "magenta", "underline": True, "target_chunk": "chunk_depaato"},
                    {"text": "department store", "color": "normal", "underline": False},
                    {"text": "(i)", "color": "red", "underline": True, "target_chunk": "zero_ga"},
                    {"text": "went, and then", "color": "cyan", "underline": True, "target_chunk": "chunk_itte"}
                ]
            },
            {
                "clause": 2,
                "tokens": [
                    {"text": "(i)", "color": "red", "underline": True, "target_chunk": "zero_ga"},
                    {"text": "did", "color": "normal", "underline": False},
                    {"text": "shopping.", "color": "orange", "underline": True, "target_chunk": "chunk_kaimono"}
                ]
            }
        ],
        "natural_translation": "昨天去了百货商店，买了东西。",
        "cognitive_note": "【て形的时间链条】「〜て」就像一根时间链条，把两个小句串在一起。时态只在整句最后一个动词（「しました」）上体现，前面的「行って」只负责传递动作相继完成的逻辑关系。"
    }
]

os.makedirs('data', exist_ok=True)
with open('data/exemplars.json', 'w', encoding='utf-8') as f:
    json.dump(exemplars, f, ensure_ascii=False, indent=2)

print(f"Saved {len(exemplars)} rich syntax exemplars into data/exemplars.json successfully!")
