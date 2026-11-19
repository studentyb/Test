Output the test plan as strictly valid JSON. All naming fields (module_id, module_name, feature_id, feature_name) must use snake_case or PascalCase with no spaces.

**JSON Structure**:
- `project_name`: Project name.
- `project_describe`: Brief description of the project.
- `supplementary_info`: **[Global Context]** — Environment, frameworks, global rules, common return structures.
- `modules`: List of modules.
  - `module_id`: Module identifier.
  - `module_name`: Module name.
  - `description`: Module responsibility.
  - `shared_context`: **[Module Context]** — Key class/DTO definitions with fields, constants with exact values, regex patterns, algorithms, edge case rules. This is the knowledge base for all Features in this module.
  - `features`: List of features.
    - `feature_id`: Feature identifier.
    - `feature_name`: Feature name.
    - `description`: What this feature does.
    - `methods`: Methods to be tested.
      - `signature`: Accurate signature — `Class.method(param: Type) -> Return` or `module.function(param: Type) -> Return` for Python module-level functions.
      - `description`: Role of the method.
    - `reqs`: Requirement fragments (goal, constraints, steps with exact formulas/logic, exceptions with edge cases).
    - `dependencies`: External method signatures to be mocked.
  - `unmapped_step`: Requirements not mapped to any Feature.
  - `unjustified_method`: Class diagram methods not included in any Feature.

```json
{
    "project_name": "ReadTime Tool",
    "project_describe": "A tool to estimate reading time for various text formats.",
    "supplementary_info": "1. Environment: Python 3.9, Pytest, BeautifulSoup4. \n2. Global Return: class Result { seconds: int, text: str }.",
    "modules": [{
       "module_id": "processing",
       "module_name": "ContentProcessing",
       "description": "Core text parsing and time calculation logic.",
       "shared_context": "1. Constants: WPM_DEFAULT = 265, IMAGE_SECONDS = 12. \n2. Regex: WORD_SPLIT = re.compile(r'\\W+'). \n3. Edge case: trailing punctuation after split produces empty string, counts as 1 word.",
       "features": [{
             "feature_id": "process_html",
             "feature_name": "process_html",
             "description": "Parse HTML string and calculate reading time.",
             "methods": [{
                "signature": "api.of_html(html: str, wpm: int=265) -> Result",
                "description": "Public API entry point for HTML input."
             },{
                "signature": "utils.parse_html(html: str) -> List[Element]",
                "description": "Strip HTML tags and extract image count."
             }],
             "reqs": [{
                "goal": "Calculate reading time for HTML with images",
                "constraints": "Input is a valid HTML string",
                "steps": "1. Strip HTML tags, extract plain text. 2. Count words using regex \\W+. 3. Count <img> tags. 4. Apply formula: ceil(word_count / wpm * 60) + image_count * 12.",
                "exceptions": "Empty HTML returns Result(seconds=0). Null input raises ValueError.",
                "dependsOn": null
             }],
             "dependencies": ["external_lib.parse(html) -> Document"]
          }],
       "unmapped_step": [],
       "unjustified_method": []
    }]
}
```
