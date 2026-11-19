# Objective
Given the **Requirements**, **Function Signature**, and **Retrieved Historical Examples**, you must identify necessary relationships between inputs and outputs. You will strictly follow a 4-step reasoning process: **Understand -> Extract -> Generate -> Verify**, and output the final result in JSON format.

---

# Context Data

## 1. Requirements (Business Logic) and Function Signature (Interface)
```text
{{sut}}
```

## 2. Retrieved Similar Examples (Few-Shot Reference)
*Use these examples to understand the expected depth and logic style, but do not copy them directly.*
```java
{{retrieved_examples_json}}
```
---

# Reasoning Workflow (Step-by-Step)

### Step 1: Understand (Analysis)
Analyze the function deeply. Do not output this step, but think silently:
1.  **Inputs**: What are the data types? What are the valid ranges (e.g., age > 0)? What are the boundary constraints?
2.  **Observable Outputs**: Apart from the `return` value, are there **side effects**? (e.g., database updates, file creation, log printing, state changes).
3.  **Core Functionality**: Is it a calculation? A transformation? A filter? A validation?

### Step 2: Extract (Pattern Recognition)
Identify the properties of the logic. Ask yourself:
*   **Permutation**: Does the order of elements matter? (e.g., `sum([a,b]) == sum([b,a])`)
*   **Inclusion**: If I search for a subset, should the result be a subset of the full search?
*   **Additivity**: Does `f(a + b)` equal `f(a) + f(b)`?
*   **Idempotency**: Does calling the function twice change anything?
*   **Exclusive**: If I exclude an item from input, should it vanish from output?

### Step 3: Generate (Formulation)
Construct the Metamorphic Relation (MR):
*   **Source Input ($I_s$)**: A valid base input.
*   **Transformation ($T$)**: How to modify $I_s$ to get **Follow-up Input ($I_f$)**. (e.g., "Add a duplicate item", "Multiply price by 2").
*   **Expected Relation ($R$)**: The strict mathematical or logical relationship between **Source Output ($O_s$)** and **Follow-up Output ($O_f$)**.

### Step 4: Verify (Counter-Example Check) -- CRITICAL
Before finalizing, try to **break** your own MR.
*   *Thought Experiment*: "If I follow this relation, is there *any* edge case where it fails?"
*   *Example*: You might think "Double the input -> Double the output".
    *   *Counter-Example*: What if there is a maximum cap? If Input=90, Max=100. Double(90)=180 -> Output is capped at 100. 100 != 2 * 90.
*   *Action*: If a simple counter-example exists, refine constraints or discard the MR.

---

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