import asyncio
import os
import json
import edge_tts

async def precompute():
    os.makedirs('assets/audio', exist_ok=True)
    with open('data/exemplars.json', 'r', encoding='utf-8') as f:
        exemplars = json.load(f)
    
    print(f"Precomputing audio for {len(exemplars)} exemplars...")
    for item in exemplars:
        filename = f"assets/audio/{item['id']}.mp3"
        if not os.path.exists(filename):
            print(f"Generating {item['id']}: {item['sentence_raw']}")
            comm = edge_tts.Communicate(item['sentence_raw'], 'ja-JP-NanamiNeural', rate='-4%')
            await comm.save(filename)
        else:
            print(f"Already exists: {item['id']}")

    print("All exemplar audio ready!")

if __name__ == '__main__':
    asyncio.run(precompute())
