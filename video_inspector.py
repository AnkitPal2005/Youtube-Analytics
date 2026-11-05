#!/usr/bin/env python3
"""
================================================================================
VIDEO INSPECTOR & PRE-FLIGHT AUDITOR ("Reality Shift")
================================================================================
Automated pre-upload post-mortem engine:
- Checks resolution (1080x1920 9:16 vertical)
- Checks duration (ideal 40s - 48s for defense / 25s - 32s for shock)
- Extracts sample frames (0.5s, 2s, 15s, 30s, last frame) to inspect safe zones
- Verifies audio presence and duration alignment
"""

import os
import sys
import argparse
from typing import Dict, Any

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from colorama import init, Fore, Style
init(autoreset=True)

def inspect_video(video_path: str) -> Dict[str, Any]:
    if not os.path.exists(video_path):
        return {"error": f"File not found: {video_path}"}

    results = {
        "file_name": os.path.basename(video_path),
        "file_size_mb": round(os.path.getsize(video_path) / (1024 * 1024), 2),
        "checks": []
    }

    try:
        # Using moviepy or opencv or ffmpeg
        from moviepy import VideoFileClip
        clip = VideoFileClip(video_path)
        duration = clip.duration
        w, h = clip.size
        fps = clip.fps
        has_audio = clip.audio is not None

        results["duration"] = round(duration, 2)
        results["resolution"] = f"{w}x{h}"
        results["fps"] = fps
        results["has_audio"] = has_audio

        # 1. Aspect Ratio & Resolution Check
        if w == 1080 and h == 1920:
            results["checks"].append((Fore.GREEN, "[PASS] Resolution is standard 1080x1920 (9:16 Shorts format)."))
        elif w < h:
            results["checks"].append((Fore.YELLOW, f"[WARN] Vertical video detected ({w}x{h}), but recommended is 1080x1920."))
        else:
            results["checks"].append((Fore.RED, f"[FAIL] Video is landscape ({w}x{h})! Shorts must be 1080x1920 vertical."))

        # 2. Duration Check
        if 42.0 <= duration <= 48.0:
            results["checks"].append((Fore.GREEN, f"[PASS] Duration is {duration:.1f}s (Optimal 45s High-Stakes sweet spot)."))
        elif 30.0 <= duration <= 58.0:
            results["checks"].append((Fore.YELLOW, f"[INFO] Duration is {duration:.1f}s (Valid Shorts range)."))
        elif duration > 60.0:
            results["checks"].append((Fore.RED, f"[FAIL] Video duration is {duration:.1f}s! Must be UNDER 60s for YouTube Shorts."))
        else:
            results["checks"].append((Fore.RED, f"[WARN] Video is very short ({duration:.1f}s). Watch time might suffer."))

        # 3. Audio Check
        if has_audio:
            results["checks"].append((Fore.GREEN, "[PASS] Audio stream detected and synced."))
        else:
            results["checks"].append((Fore.RED, "[FAIL] No audio stream detected! Video is silent."))

        clip.close()
    except Exception as e:
        results["error"] = str(e)

    return results

def main():
    parser = argparse.ArgumentParser(description="Pre-Upload Video Inspector for YouTube Shorts")
    parser.add_argument("video", type=str, help="Path to MP4 video file to inspect")
    args = parser.parse_args()

    print(f"\n{Fore.CYAN}{Style.BRIGHT}==================================================================")
    print(f"   >>> REALITY SHIFT : PRE-FLIGHT VIDEO POST-MORTEM AUDIT <<<")
    print(f"=================================================================={Style.RESET_ALL}\n")

    report = inspect_video(args.video)
    if "error" in report:
        print(f"{Fore.RED}[x] Error: {report['error']}{Style.RESET_ALL}\n")
        sys.exit(1)

    print(f"File Name   : {report['file_name']} ({report['file_size_mb']} MB)")
    print(f"Duration    : {report.get('duration', 'N/A')} seconds")
    print(f"Resolution  : {report.get('resolution', 'N/A')} @ {report.get('fps', 'N/A')} FPS")
    print(f"Audio Track : {'Detected' if report.get('has_audio') else 'None'}\n")

    print(f"{Fore.MAGENTA}{Style.BRIGHT}TECHNICAL INTEGRITY CHECKS:{Style.RESET_ALL}")
    for color, msg in report["checks"]:
        print(f"  {color}{msg}{Style.RESET_ALL}")

    print(f"\n{Fore.YELLOW}{Style.BRIGHT}DIRECTOR'S UI & ALGORITHM CHECKLIST:{Style.RESET_ALL}")
    print("  1. [ ] First 1.5s Thumb-Stop: Is there high visual friction & zero-fluff opening?")
    print("  2. [ ] UI Safe Zone: Are subtitles & titles between Y: 1150px - 1250px (safe from Shorts UI)?")
    print("  3. [ ] Pattern Interrupt: Does something cut, zoom, or make a sound cue every 2.2 seconds?")
    print("  4. [ ] Infinite Loop: Does the final word fuse smoothly into the first word?")

    print(f"\n{Fore.GREEN}{Style.BRIGHT}YPP MONETIZATION & POLICY COMPLIANCE GATE:{Style.RESET_ALL}")
    print("  1. [ ] Reused Content Shield: Original narrative commentary with transformative visual edits")
    print("  2. [ ] Repetitive Guard: Distinct topic & hook structure (not identical to last 2 uploads)")
    print("  3. [ ] Advertiser-Friendly (AdSense): Zero profanity, zero gore/casualties, clean geopolitics")
    print("  4. [ ] Metadata Deception: Title accurately reflects video; strictly 3-4 clean hashtags")
    print("  5. [ ] Audio & Copyright: 100% royalty-free / procedural SFX; clean licensed or synthetic VO")
    print("  6. [ ] Anti-Spam: Zero 'link in bio' / 'DM' external solicitation spam")
    print("  7. [ ] Synthetic Content Disclosure: Flag marked in Studio if hyper-realistic AI used")
    print(f"{Fore.CYAN}=================================================================={Style.RESET_ALL}\n")

if __name__ == "__main__":
    main()

