import asyncio
import os
import json
import hashlib
import re
import edge_tts

AUDIO_DIR = os.path.join(os.path.dirname(__file__), 'assets', 'audio')
os.makedirs(AUDIO_DIR, exist_ok=True)

VOICES = [
    'ja-JP-NanamiNeural', # Female
    'ja-JP-KeitaNeural'    # Male
]

def clean_text(raw):
    t = re.sub(r'<[^>]*>', '', raw)
    t = re.sub(r'[!！\s　。、.?,?？]', '', t)
    return t.strip()

def get_cache_path(voice, text):
    c = clean_text(text)
    key = f"{voice}_{c}"
    h = hashlib.md5(key.encode('utf-8')).hexdigest()
    return os.path.join(AUDIO_DIR, f"{h}.mp3"), h, c

async def generate_one(sem, voice, text, label=""):
    c_path, h, c_text = get_cache_path(voice, text)
    if os.path.exists(c_path) and os.path.getsize(c_path) > 1000:
        return True
    
    async with sem:
        try:
            print(f"[{voice[-12:-6]}] Generating: {c_text} ({label})")
            comm = edge_tts.Communicate(c_text, voice, rate='-4%')
            await comm.save(c_path)
            return True
        except Exception as e:
            print(f"Error generating '{c_text}': {e}")
            return False

async def main():
    sem = asyncio.Semaphore(4) # 4 concurrent requests
    tasks = []

    # 1. Key exemplars
    with open('data/exemplars.json', 'r', encoding='utf-8') as f:
        exemplars = json.load(f)
    for ex in exemplars:
        for v in VOICES:
            tasks.append(generate_one(sem, v, ex['sentence_raw'], f"Exemplar {ex['id']}"))

    # 2. Lessons 1 - 6 Basic sentences and dialogues
    with open('data/lessons.json', 'r', encoding='utf-8') as f:
        lessons = json.load(f)

    for les in lessons[:6]: # Lessons 1 to 6
        # Basic 4
        for b4 in les.get('basic4', []):
            for v in VOICES:
                tasks.append(generate_one(sem, v, b4['jp_clean'], f"L{les['number']} Basic"))
        # Basic Dialogues
        for bc in les.get('basicc', []):
            for v in VOICES:
                tasks.append(generate_one(sem, v, bc['jp_clean'], f"L{les['number']} Dlg"))
        # Applied Dialogues
        for sec in les.get('context_sections', []):
            for item in sec:
                if item.get('type') == 'dialogue' and item.get('jp_clean'):
                    for v in VOICES:
                        tasks.append(generate_one(sem, v, item['jp_clean'], f"L{les['number']} App"))

    print(f"Total audio targets queued: {len(tasks)}")
    results = await asyncio.gather(*tasks)
    print(f"Finished! Successfully cached {sum(1 for r in results if r)} files.")

if __name__ == '__main__':
    asyncio.run(main())
