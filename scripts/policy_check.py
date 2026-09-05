import json, re, os
import yaml

with open("config/config.yaml", 'r') as f:
    CONFIG = yaml.safe_load(f)

class YouTubePolicyGate:
    def run_full_check(self, job_id):
        script_path = f"jobs/{job_id}/script/script.txt"
        if not os.path.exists(script_path): return True
        with open(script_path, 'r') as f:
            script = f.read().lower()
        bad_words = CONFIG['youtube_hard_rules']['profanity']['blocked_words']
        for word in bad_words:
            if word in script:
                print(f"🚨 BLOCKED: Profanity '{word}'")
                return False
        bad_phrases = CONFIG['youtube_hard_rules']['financial_claims']['prohibited_phrases']
        for phrase in bad_phrases:
            if phrase in script:
                print(f"🚨 BLOCKED: Financial Guarantee '{phrase}'")
                return False
        return True