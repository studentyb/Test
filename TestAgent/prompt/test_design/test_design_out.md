Output strictly valid JSON array. Each element corresponds to one focal method.

Rules:

- Category: Positive / Negative / Boundary (add Metamorphic when MR is provided)
- For Metamorphic cases, replace `inputs` with `source_inputs` + `followup_inputs`

```json
[
  {
    "focal_method": "method_signature",
    "test_cases": [
      {
        "id": "TC_001",
        "category": "Positive",
        "arrange": {
          "inputs": [
            { "name": "param1", "value": "<img src='x.png'>word1 word2", "type": "String" }
          ],
          "mocks": [
            { "target": "module.func", "behavior": "return_value <<NEW:Result(count=1)>>" }
          ]
        },
        "asserts": [
          { "target": "result.seconds == 12" }
        ]
      }
    ]
  }
]
```
