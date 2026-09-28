#!/usr/bin/env python3
"""Local AlgoLevel short-video planner and FFmpeg renderer."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import urllib.request

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent
ROLES = ("before", "enable", "detail", "closing")
DURATIONS = (4, 7, 7, 6)
FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"


def run(args):
    subprocess.run(args, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)


def api(path, payload, binary=False):
    key = os.getenv("OPENAI_API_KEY")
    if not key:
        raise ValueError("OPENAI_API_KEY is required for the AI option")
    req = urllib.request.Request(
        "https://api.openai.com/v1/" + path,
        data=json.dumps(payload).encode(),
        headers={"Authorization": "Bearer " + key, "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=90) as response:
        return response.read() if binary else json.load(response)


def local_plan(topic):
    subject = topic.strip()[:42]
    return {
        "topic": topic,
        "format": "1080x1920, 24 seconds, 9:16",
        "voiceover": f"Let's look at {subject}. Here is the chart before and after AlgoLevel is turned on. You can inspect the displayed levels directly on your chart. See how it works at AlgoLevel dot com.",
        "caption": "See AlgoLevel on a real TradingView chart. Explore the indicator at AlgoLevel.com. #TradingView #ChartAnalysis #SupportAndResistance #AlgoLevel",
        "thumbnail": "SEE THE LEVELS",
        "scenes": [
            {"role": "before", "seconds": 4, "text": subject},
            {"role": "enable", "seconds": 7, "text": "Turn on AlgoLevel"},
            {"role": "detail", "seconds": 7, "text": "Inspect levels on the chart"},
            {"role": "closing", "seconds": 6, "text": "See AlgoLevel.com"},
        ],
    }


def ai_plan(topic):
    prompt = ("Write an AlgoLevel TradingView indicator video plan. Use only claims visible in real footage; "
              "do not invent features or claim trading profits, prediction, accuracy, or results. "
              "Four scenes, roles before/enable/detail/closing, durations 4/7/7/6 seconds. "
              "Return JSON with topic, voiceover (under 55 words), caption, thumbnail, scenes; "
              "each scene has role, seconds, text (under 42 characters). Plain English. Topic: " + topic)
    data = api("chat/completions", {"model": "gpt-4.1-mini", "response_format": {"type": "json_object"},
                                    "messages": [{"role": "user", "content": prompt}]})
    plan = json.loads(data["choices"][0]["message"]["content"])
    validate(plan)
    plan["format"] = "1080x1920, 24 seconds, 9:16"
    return plan


def validate(plan):
    scenes = plan.get("scenes")
    if not isinstance(scenes, list) or len(scenes) != 4:
        raise ValueError("Plan needs four scenes")
    for i, scene in enumerate(scenes):
        if scene.get("role") != ROLES[i] or scene.get("seconds") != DURATIONS[i]:
            raise ValueError("Scene roles/timing must be before, enable, detail, closing at 4/7/7/6 seconds")
        if not isinstance(scene.get("text"), str) or len(scene["text"]) > 42:
            raise ValueError("On-screen text must be at most 42 characters")
    for field in ("voiceover", "caption", "thumbnail"):
        if not isinstance(plan.get(field), str):
            raise ValueError("Missing plan field: " + field)
    forbidden = ("guaranteed", "risk-free", "100% accurate", "never lose", "get rich")
    combined = json.dumps(plan).lower()
    if any(term in combined for term in forbidden):
        raise ValueError("Plan contains a prohibited performance claim")


def art(text, path, demo=False, thumbnail=False):
    image = Image.new("RGB" if demo or thumbnail else "RGBA", (1080, 1920), "#07111e" if demo or thumbnail else (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 0, 1080, 225), fill="#0b1830")
    draw.text((70, 70), "ALGOLEVEL", font=ImageFont.truetype(FONT, 58), fill="#58d6c4")
    draw.rectangle((55, 1440, 1025, 1780), fill="#07111e")
    font = ImageFont.truetype(FONT, 58)
    words, lines, line = text.split(), [], ""
    for word in words:
        trial = (line + " " + word).strip()
        if draw.textbbox((0, 0), trial, font=font)[2] > 910 and line:
            lines.append(line)
            line = word
        else:
            line = trial
    lines.append(line)
    y = 1500
    for part in lines[:3]:
        draw.text((75, y), part, font=font, fill="white")
        y += 78
    if demo:
        draw.text((70, 360), "DEMO PLACEHOLDER", font=ImageFont.truetype(FONT, 55), fill="#ffbd59")
        draw.text((70, 470), "Add real AlgoLevel clips", font=ImageFont.truetype(FONT, 38), fill="white")
    if thumbnail:
        draw.text((70, 700), "TradingView indicator demo", font=ImageFont.truetype(FONT, 34), fill="#58d6c4")
    image.save(path)


def clips(demo):
    if demo:
        return [None] * 4
    catalog = json.loads((ROOT / "assets/catalog.json").read_text())
    result = []
    missing = []
    for role in ROLES:
        name = catalog.get(role, "")
        file = ROOT / "assets/clips" / name
        if not name or not file.is_file() or file.suffix.lower() not in (".mp4", ".mov", ".mkv"):
            missing.append(f"{role}: assets/clips/{name or '<unset>'}")
        result.append(file)
    if missing:
        raise FileNotFoundError("Missing real footage:\n" + "\n".join(missing) + "\nUse 'demo' to test placeholders.")
    return result


def render(plan, sources, dest, demo, voice):
    dest.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as temp:
        tmp = Path(temp)
        segments = []
        for i, (scene, source) in enumerate(zip(plan["scenes"], sources)):
            overlay = tmp / f"overlay{i}.png"
            art(scene["text"], overlay, demo=demo)
            segment = tmp / f"part{i}.mp4"
            duration = scene["seconds"]
            if source is None:
                input_args = ["-f", "lavfi", "-i", "color=c=0x14243b:s=1080x1920:r=30"]
            else:
                input_args = ["-stream_loop", "-1", "-i", str(source)]
            filter_text = "[0:v]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,setsar=1,fps=30[base];[base][1:v]overlay=0:0:format=auto,format=yuv420p[out]"
            run(["ffmpeg", "-y", "-loglevel", "error", "-filter_threads", "1", *input_args, "-loop", "1", "-i", str(overlay),
                 "-filter_complex", filter_text, "-map", "[out]", "-t", str(duration),
                 "-an", "-c:v", "libx264", "-threads", "1", "-preset", "ultrafast", "-crf", "24", "-pix_fmt", "yuv420p", str(segment)])
            segments.append(segment)
        listing = tmp / "concat.txt"
        listing.write_text("".join("file '" + str(x) + "'\n" for x in segments))
        assembled = tmp / "silent.mp4"
        run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(listing), "-c", "copy", str(assembled)])
        target = dest / "video.mp4"
        if voice:
            run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(assembled), "-i", str(voice),
                 "-map", "0:v", "-map", "1:a", "-c:v", "copy", "-c:a", "aac", "-b:a", "160k",
                 "-af", "apad", "-t", "24", str(target)])
        else:
            target.write_bytes(assembled.read_bytes())
    (dest / "plan.json").write_text(json.dumps(plan, indent=2) + "\n")
    (dest / "script.txt").write_text(plan["voiceover"] + "\n")
    (dest / "caption.txt").write_text(plan["caption"] + "\n")
    art(plan["thumbnail"], dest / "thumbnail.png", demo=demo, thumbnail=True)
    print("Created", target)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("init")
    for name in ("create", "demo"):
        p = sub.add_parser(name)
        p.add_argument("--topic", default="manual levels")
        p.add_argument("--output", default="outputs/" + name)
        p.add_argument("--voice", type=Path)
        p.add_argument("--ai-script", action="store_true")
        p.add_argument("--ai-voice", action="store_true")
    args = parser.parse_args()
    if args.command == "init":
        (ROOT / "assets/clips").mkdir(parents=True, exist_ok=True)
        print("Add real recordings to", ROOT / "assets/clips")
        return
    if args.voice and args.ai_voice:
        parser.error("Choose --voice or --ai-voice")
    sources = clips(args.command == "demo")
    plan = ai_plan(args.topic) if args.ai_script else local_plan(args.topic)
    validate(plan)
    output = Path(args.output).resolve()
    voice = args.voice
    if voice and not voice.is_file():
        parser.error("Voice file not found")
    if args.ai_voice:
        output.mkdir(parents=True, exist_ok=True)
        voice = output / "voice.mp3"
        voice.write_bytes(api("audio/speech", {"model": "tts-1", "voice": "alloy", "input": plan["voiceover"], "response_format": "mp3"}, binary=True))
    render(plan, sources, output, args.command == "demo", voice)


if __name__ == "__main__":
    try:
        main()
    except (ValueError, FileNotFoundError, subprocess.CalledProcessError) as exc:
        print("Error:", exc, file=sys.stderr)
        sys.exit(1)
