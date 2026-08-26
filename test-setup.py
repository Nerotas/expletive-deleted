#!/usr/bin/env python3
"""
Quick test of profanity detection with local audio file
"""

import os
import sys
import tempfile
import subprocess
from pathlib import Path


def test_installation():
    """Test if all dependencies are installed correctly"""
    print("""
╔════════════════════════════════════════════════════════════════╗
║   Profanity Censoring Workflow - Dependency Test               ║
╚════════════════════════════════════════════════════════════════╝
    """)

    results = {}

    # Test FFmpeg
    print("[*] Testing FFmpeg...")
    try:
        result = subprocess.run(['ffmpeg', '-version'], capture_output=True, text=True)
        if result.returncode == 0:
            version = result.stdout.split('\n')[0]
            print(f"[+] FFmpeg: OK - {version}")
            results['ffmpeg'] = True
        else:
            print("[-] FFmpeg: Failed to run")
            results['ffmpeg'] = False
    except FileNotFoundError:
        print("[-] FFmpeg: Not found in PATH")
        results['ffmpeg'] = False

    # Test Python Whisper
    print("\n[*] Testing Python: openai-whisper...")
    try:
        import whisper
        print(f"[+] Whisper: OK - {whisper.__version__ if hasattr(whisper, '__version__') else 'installed'}")
        results['whisper'] = True
    except ImportError:
        print("[-] Whisper: Not installed - pip install openai-whisper")
        results['whisper'] = False

    # Test Python better-profanity
    print("\n[*] Testing Python: better-profanity...")
    try:
        from better_profanity import profanity
        print("[+] better-profanity: OK")
        results['profanity'] = True
    except ImportError:
        print("[-] better-profanity: Not installed - pip install better-profanity")
        results['profanity'] = False

    # Test NumPy (required by Whisper)
    print("\n[*] Testing Python: numpy...")
    try:
        import numpy
        print("[+] NumPy: OK")
        results['numpy'] = True
    except ImportError:
        print("[-] NumPy: Not installed - pip install numpy")
        results['numpy'] = False

    # Summary
    print(f"\n{'='*60}")
    passed = sum(1 for v in results.values() if v)
    total = len(results)
    print(f"Results: {passed}/{total} passed")
    print(f"{'='*60}")

    if all(results.values()):
        print("\n[✓] All dependencies installed and working!")
        return True
    else:
        print("\n[!] Some dependencies are missing or not working properly.")
        print("\nRun setup: python setup.py")
        return False


def test_profanity_detection():
    """Test profanity detection functionality"""
    print("\n\n╔════════════════════════════════════════════════════════════════╗")
    print("║   Profanity Detection Test                                     ║")
    print("╚════════════════════════════════════════════════════════════════╝\n")

    try:
        from better_profanity import profanity

        profanity.load_censor_words()

        test_phrases = [
            "This is clean text",
            "This is a damn bad word",
            "What the hell is this",
            "That's so awesome!",
            "He used profanity in his speech",
        ]

        print("Testing profanity detection:\n")
        for phrase in test_phrases:
            is_profane = profanity.contains_profanity(phrase)
            censored = profanity.censor(phrase)
            status = "[!] PROFANITY DETECTED" if is_profane else "[✓] Clean"
            print(f"{status}")
            print(f"  Original: {phrase}")
            print(f"  Censored: {censored}")
            print()

        return True
    except Exception as e:
        print(f"[-] Profanity detection test failed: {e}")
        return False


def test_whisper_transcription():
    """Test Whisper transcription with a sample audio"""
    print("\n╔════════════════════════════════════════════════════════════════╗")
    print("║   Whisper Transcription Test                                   ║")
    print("╚════════════════════════════════════════════════════════════════╝\n")

    try:
        import whisper

        # Check if user wants to test with their file
        test_file = "C:\\Users\\Nerot\\Downloads\\temp\\ready\\ProfanityTest.mp3"

        if os.path.exists(test_file):
            print(f"[*] Found test file: {test_file}")
            print("[*] This would transcribe the audio - skip for now (large download)")
            print("[!] First Whisper run downloads model (~140MB)")
            print("\nTo test later:")
            print(f"  python -c \"import whisper; result = whisper.load_model('tiny').transcribe('{test_file}'); print(result['text'][:100])\"")
            return True
        else:
            print(f"[-] Test file not found: {test_file}")
            print("[*] Whisper model will be downloaded on first use (~140MB)")
            return False

    except Exception as e:
        print(f"[-] Whisper test failed: {e}")
        return False


def main():
    success = test_installation()

    if success:
        success = test_profanity_detection() and success
        success = test_whisper_transcription() and success

    print(f"\n{'='*60}")
    if success:
        print("[✓] Setup test completed successfully!")
        print("\nYou can now run:")
        print("  python censor_profanity.py input.mp4 output.mp4")
        print("  .\\convert-profanity-censor.ps1")
    else:
        print("[✗] Setup test found issues")
        print("\nRun: python setup.py")
    print(f"{'='*60}\n")

    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
