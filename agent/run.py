from agent.graph import build_graph


def main():
    app = build_graph()
    print("RentGuard agent — ask about a building's HPD/311 history (Ctrl+C to quit)\n")

    while True:
        zip_code = input("ZIP filter (or Enter for none): ").strip() or None
        question = input("Question: ").strip()
        if not question:
            continue

        result = app.invoke({
            "question": question,
            "zip_code": zip_code,
            "retrieved_docs": [],
            "answer": "",
            "guardrail_notes": [],
            "attempt": 0,
        })

        print("\n--- Answer ---")
        print(result["answer"])
        if result["guardrail_notes"]:
            print(f"\n[guardrail notes: {result['guardrail_notes']}]")
        print("\n" + "-" * 60 + "\n")


if __name__ == "__main__":
    main()
