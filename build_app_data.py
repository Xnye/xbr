import os
import sys
import re
import csv
import json
import yaml
import pykakasi

sys.stdout.reconfigure(encoding='utf-8')

# Setup pykakasi for romaji generation
kks = pykakasi.kakasi()

def kana_to_romaji(text):
    if not text:
        return ""
    res = kks.convert(text)
    return " ".join([item['hepburn'] for item in res if item['hepburn']])

def clean_ruby_markup(text):
    """
    Parses !Kanji(kana) into structured tokens.
    Returns:
      - raw_clean: plain Japanese text without markup
      - html_ruby: HTML string with <ruby>Kanji<rt>kana</rt></ruby>
      - hiragana_only: only kana reading
    """
    if not text:
        return "", "", ""
    
    # Replace !Word(kana) with ruby
    def sub_ruby(match):
        kanji = match.group(1)
        kana = match.group(2)
        return f"<ruby>{kanji}<rt>{kana}</rt></ruby>"
    
    html_ruby = re.sub(r'!([^\(!\s]+)\(([^)]+)\)', sub_ruby, text)
    raw_clean = re.sub(r'!([^\(!\s]+)\(([^)]+)\)', r'\1', text)
    hiragana_only = re.sub(r'!([^\(!\s]+)\(([^)]+)\)', r'\2', text)
    
    return raw_clean, html_ruby, hiragana_only

print("Loading raw files from temp_learnjapan...")

with open('temp_learnjapan/_data/lessons.yml', 'r', encoding='utf-8') as f:
    lessons_raw = yaml.safe_load(f)

grammar_by_lesson = {}
with open('temp_learnjapan/_data/grammar.csv', 'r', encoding='utf-8') as f:
    reader = csv.DictReader(f)
    for row in reader:
        les_id = row['lesson'].strip()
        les_num = int(les_id) if les_id.isdigit() else 0
        if les_num not in grammar_by_lesson:
            grammar_by_lesson[les_num] = []
        grammar_by_lesson[les_num].append({
            'idx': row['idx'].strip(),
            'expression': row['expression'].strip(),
            'shortexplain': row['shortexplain'].strip(),
            'explanation': row['explanation'].strip()
        })

words_by_lesson = {}
with open('temp_learnjapan/_data/words.csv', 'r', encoding='utf-8') as f:
    reader = csv.DictReader(f)
    for row in reader:
        les_id = row['lesson'].strip()
        les_num = int(les_id) if les_id.isdigit() else 0
        if les_num not in words_by_lesson:
            words_by_lesson[les_num] = []
        words_by_lesson[les_num].append({
            'word': row['word'].strip(),
            'kana': row['kana'].strip(),
            'kanji': row['kanji'].strip(),
            'pos': row['pos'].strip(),
            'desc': row['desc'].strip()
        })

print(f"Loaded {len(lessons_raw)} lessons.")

parsed_lessons = []

for num in range(1, 49):
    key = f"l{num}"
    if key not in lessons_raw:
        continue
    raw_l = lessons_raw[key]
    
    # Parse title
    title_raw = raw_l.get('title', '').strip()
    title_clean, title_ruby, _ = clean_ruby_markup(title_raw)
    title_romaji = kana_to_romaji(title_clean)
    
    # Parse Basic4
    b4_lines = [l.strip().lstrip('>').lstrip('*').strip() for l in raw_l.get('basic4', '').split('\n') if l.strip()]
    b4t_lines = [l.strip().lstrip('>').lstrip('*').strip() for l in raw_l.get('basic4t', '').split('\n') if l.strip()]
    
    basic4 = []
    for i in range(len(b4_lines)):
        jp_raw = b4_lines[i]
        zh = b4t_lines[i] if i < len(b4t_lines) else ""
        clean, ruby, hira = clean_ruby_markup(jp_raw)
        romaji = kana_to_romaji(clean)
        basic4.append({
            'id': f"b4_{num}_{i+1}",
            'jp_raw': jp_raw,
            'jp_clean': clean,
            'jp_ruby': ruby,
            'romaji': romaji,
            'zh': zh
        })
    
    # Parse Basic Conversation (A, B, C, D)
    bc_lines = [l.strip().lstrip('*').strip() for l in raw_l.get('basicc', '').split('\n') if l.strip()]
    bct_lines = [l.strip().lstrip('*').strip() for l in raw_l.get('basicct', '').split('\n') if l.strip()]
    
    basicc = []
    current_group = ""
    for i in range(len(bc_lines)):
        line_jp = bc_lines[i]
        line_zh = bct_lines[i] if i < len(bct_lines) else ""
        
        # Check group marker e.g. Ａ, Ｂ, Ｃ, Ｄ
        group_match = re.match(r'^([Ａ-ＤA-D])\s*(.*)', line_jp)
        if group_match:
            current_group = group_match.group(1)
            line_jp = group_match.group(2)
        
        # Check speaker e.g. 甲： or 乙：
        speaker = ""
        speaker_match = re.match(r'^(甲|乙|李|小野|森|林|吉田|長島|田中|スミス|王|陳|金|デュポン)\s*[:：]\s*(.*)', line_jp)
        if speaker_match:
            speaker = speaker_match.group(1)
            line_jp = speaker_match.group(2)
        
        clean, ruby, _ = clean_ruby_markup(line_jp)
        romaji = kana_to_romaji(clean)
        
        basicc.append({
            'id': f"bc_{num}_{i+1}",
            'group': current_group,
            'speaker': speaker,
            'jp_raw': line_jp,
            'jp_clean': clean,
            'jp_ruby': ruby,
            'romaji': romaji,
            'zh': line_zh
        })
    
    # Parse Applied Context (应用课文)
    contitle_raw = raw_l.get('contitle', '').strip()
    contitle_clean, contitle_ruby, _ = clean_ruby_markup(contitle_raw)
    contitlet = raw_l.get('contitlet', '').strip()
    
    ctx_blocks = raw_l.get('context', '').split('---')
    ctxt_blocks = raw_l.get('contextt', '').split('---')
    
    context_sections = []
    for b_idx in range(len(ctx_blocks)):
        ctx_b = ctx_blocks[b_idx]
        ctxt_b = ctxt_blocks[b_idx] if b_idx < len(ctxt_blocks) else ""
        
        j_lines = [l.strip().lstrip('*').strip() for l in ctx_b.split('\n') if l.strip()]
        z_lines = [l.strip().lstrip('*').strip() for l in ctxt_b.split('\n') if l.strip()]
        
        dialogues = []
        for j_i in range(len(j_lines)):
            jl = j_lines[j_i]
            zl = z_lines[j_i] if j_i < len(z_lines) else ""
            
            if jl == '-' or jl == '':
                # Narration / scene description from zh
                if zl:
                    dialogues.append({
                        'type': 'narration',
                        'zh': zl
                    })
                continue
            
            speaker = ""
            sp_match = re.match(r'^!?([^：:]+)[：:]\s*(.*)', jl)
            if sp_match:
                sp_raw = sp_match.group(1)
                sp_clean, sp_ruby, _ = clean_ruby_markup(sp_raw)
                speaker = sp_clean
                jl = sp_match.group(2)
            
            # Clean speaker from zh if present
            zh_clean = zl
            zh_sp_match = re.match(r'^([^：:]+)[：:]\s*(.*)', zl)
            if zh_sp_match:
                zh_clean = zh_sp_match.group(2)
            
            clean, ruby, _ = clean_ruby_markup(jl)
            romaji = kana_to_romaji(clean)
            
            dialogues.append({
                'type': 'dialogue',
                'speaker': speaker,
                'jp_raw': jl,
                'jp_clean': clean,
                'jp_ruby': ruby,
                'romaji': romaji,
                'zh': zh_clean
            })
        
        context_sections.append(dialogues)
    
    # Grammar
    grammar_items = grammar_by_lesson.get(num, [])
    
    # Words
    raw_words = words_by_lesson.get(num, [])
    cleaned_words = []
    for w in raw_words:
        w_word = w['word']
        w_clean, w_ruby, _ = clean_ruby_markup(w_word)
        # extract pitch accent from kana, e.g. ちゅうごくじん@4
        kana_raw = w['kana']
        pitch = ""
        if '@' in kana_raw:
            parts = kana_raw.split('@')
            kana_pure = parts[0].strip()
            pitch = parts[1].strip()
        else:
            kana_pure = kana_raw.strip()
            
        cleaned_words.append({
            'word_clean': w_clean,
            'word_ruby': w_ruby,
            'kana': kana_pure,
            'pitch': pitch,
            'kanji': w['kanji'].strip(),
            'pos': w['pos'].strip(),
            'desc': w['desc'].strip(),
            'romaji': kana_to_romaji(kana_pure)
        })
    
    parsed_lessons.append({
        'number': num,
        'title_clean': title_clean,
        'title_ruby': title_ruby,
        'title_romaji': title_romaji,
        'basic4': basic4,
        'basicc': basicc,
        'contitle': contitle_clean,
        'contitle_ruby': contitle_ruby,
        'contitlet': contitlet,
        'context_sections': context_sections,
        'grammar': grammar_items,
        'words': cleaned_words
    })

print(f"Processed {len(parsed_lessons)} complete lessons.")

os.makedirs('data', exist_ok=True)
with open('data/lessons.json', 'w', encoding='utf-8') as f:
    json.dump(parsed_lessons, f, ensure_ascii=False, indent=2)

print("Saved data/lessons.json successfully!")
