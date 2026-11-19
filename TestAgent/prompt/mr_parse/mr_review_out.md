{
    "reviews": [
        {
            "mr_id": 1,
            "verdict": "Valid",
            "comments": "Correctly identifies the metamorphic relation."
        },
        {
            "mr_id": 2,
            "verdict": "Invalid",
            "issue_type": "Parameter Hallucination",
            "comments": "The function signature does not include 'temperature'.",
            "counter_example": "calc(x, temperature=0.5) raises TypeError",
            "action": "DELETE"
        }
    ]
}
