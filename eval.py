import asyncio
import urllib.request
import urllib.error
from main import Claim, find_contradictions, DEFAULT_HOST

TEST_CASES = [
    ("The capital of France is Paris.", "The capital of France is Berlin.", True),
    ("The Matrix was released in 1999.", "The Matrix came out in 2003.", True),
    ("I am currently living in New York.", "I have never been to New York.", True),
    ("Paris is the capital of France.", "Paris has a population of over 2 million.", False),
    ("Water boils at 100 degrees Celsius.", "Water freezes at 0 degrees Celsius.", False),
    ("I love eating pizza.", "My favorite food is sushi.", False),
]

async def run_eval():
    try:
        urllib.request.urlopen(f"{DEFAULT_HOST}/api/tags", timeout=2.0)
    except Exception:
        print("Error: Ollama must be running to execute the evaluation.")
        return

    print(f"Running evaluation on {len(TEST_CASES)} pairs...\n")
    passed = 0
    for i, (text1, text2, expected) in enumerate(TEST_CASES):
        c1 = Claim(id=f"c1_{i}", text=text1, turn_index=0)
        c2 = Claim(id=f"c2_{i}", text=text2, turn_index=1)
        
        results = await find_contradictions([c1, c2])
        result = results[0] if results else None
        
        actual = result is not None and result.contradictory
        status = "[PASS]" if actual == expected else "[FAIL]"
        if actual == expected: passed += 1
            
        print(f"Test {i+1}: {status}\n  Claim 1: {text1}\n  Claim 2: {text2}\n  Expected: {expected} | Actual: {actual}")
        if result: print(f"  Explanation: {result.explanation}")
        print("-" * 40)
        
    print(f"\nEvaluation Complete: {passed}/{len(TEST_CASES)} passed.")

if __name__ == "__main__":
    asyncio.run(run_eval())
