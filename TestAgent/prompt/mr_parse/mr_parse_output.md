# Output Format

Output **ONLY** a valid JSON object containing a list of MRs. Do not include markdown code blocks (```json) or conversational filler.

**JSON Schema:**
```json
[
  {
    "mr_id": "MR_001",
    "name": "Short descriptive name (e.g., Order Independence)",
    "reasoning": {
      "input_analysis": "Brief analysis of input types and constraints.",
      "transformation_logic": "Explain how the input is modified.",
      "output_prediction": "Explain why the output should behave this way."
    },
    "technical_definition": {
      "source_input": "Description of valid starting input",
      "follow_up_input": "Precise logic to generate follow-up input (e.g., input_list.reverse())",
      "assertion": "Python-like boolean expression comparing outputs (e.g., output_source == output_followup)"
    },
    "verification": {
      "potential_counter_example": "Describe a scenario where this might fail (Self-Correction)."
    }
  }
]
```