# Specification: Multi-Section Retrieval for Cross-Section Comparison Questions

## 1. Context and Problem

The in-context cross-passage synthesis prompt contract is active on `main` (commit `8e32da5`), permitting the model to perform cross-passage comparison and synthesis between distinct sections of a paper (such as comparing claims in the Abstract against empirical findings in the Results section) under strict grounding constraints.

However, cross-section comparison queries routinely fail and trigger the standard system fallback sentence:
> `"The uploaded paper does not contain information to answer this question."`

This failure occurs because a single dense vector retrieval query cannot adequately span distinct document sections that differ in vocabulary and semantic framing. When a user asks a comparative question such as:
`"Does the abstract accurately summarize all the main results and findings reported in the paper?"`
the single rewritten query prioritizes results-heavy passages, completely crowding out abstract passages from the top retrieval ranks.

### Empirical Diagnostic Evidence
In an empirical diagnostic evaluation (`/tmp/diagnose_author_query.py`) on the 6-page indexed paper (`cbbbf2b10fc47efb987348bef1212ba9e803f3cbc48366c8c33111d429f4d93c` – *"Impact of mass chemotherapy for the control of filariasis on geohelminth infections in Sri Lanka"*), the query rewriter generated:
`"Does the abstract summarize all main results and findings?"`

Evaluating the top 10 retrieved chunks (`top_k=10`) revealed:
- **Abstract chunks in top 10**: 0 (zero abstract passages retrieved).
- **Cosine distances**: Ranged from `0.7599` to `0.8007` against the configured citation distance cutoff of `0.87` (`CITATION_MAX_DISTANCE`).
- **Results & background passages**: Completely dominated ranks 1 through 10 (Rank 1 distance `0.7599` on Page 4; Rank 7 distance `0.7833` on Page 3).

Because the Abstract was entirely absent from the top retrieved excerpts passed into `<RETRIEVED_CHUNKS>`, the LLM possessed only one half of the required comparative context and correctly triggered the anti-hallucination fallback sentence.

---

## 2. Trigger

To support cross-section comparative inquiries without fragile client-side or server-side heuristics, the intent classifier and query rewriter (`backend/app/services/classifier.py`) will be extended via structured JSON output.

### Structured Output Schema Extension
The `ClassifierResult` Pydantic model will introduce two new fields alongside the existing fields:
```python
class ClassifierResult(BaseModel):
    intent: IntentType = Field(default="document_question")
    query: str = Field(default="")
    is_comparative: bool = Field(default=False)
    comparison_targets: list[str] = Field(default_factory=list)
```

### Invariants:
1. **Existing Contract Preserved**: The existing `intent` (`chat`, `document_overview`, `document_question`, `outside_paper`) and `query` fields retain their existing semantics, validation, and string formats.
2. **Strict Classifier Triggering**: Triggering multi-section retrieval relies strictly on `is_comparative is True` and the explicit targets enumerated in `comparison_targets` (e.g., `["abstract", "results"]`).
3. **No Heuristic Bypasses**: No keyword matching, token blacklists, word lists, or regular expressions shall be used to detect comparison intent. The classifier prompt alone is updated to output structured boolean and target list signals.

---

## 3. Section Identification

Cross-section comparison requires resolving candidate passages for target sections from verified document extraction artifacts.

### Exact Sources for Section Identification:
1. **Abstract Target (`"abstract"`)**:
   - Primary Source: The structured summary cache header / metadata block (`header.abstract` or `title_authors_abstract` parsed during initial ingestion).
   - Secondary Source: The isolated Page 1 header block extracted by `pdf_parser` and verified by `HeaderMetadata` in `metadata_service`.
   - Vector Seed: Querying the document collection using the exact abstract text prefix or explicit section anchor `"Abstract"`.
2. **Results Target (`"results"`)**:
   - Primary Source: Chunks tagged with `section: "results"` or headings identified during section parsing (`extract_sections` / `rebuild_text_from_chroma`).
   - Vector Seed: Querying the document collection using explicit empirical target terms derived from section anchors (`"Results"`, `"Findings"`, `"Prevalence"`).

### Missing Target Section Policy:
- If a target section (e.g., Abstract or Results) cannot be identified in the document metadata or extracted text structure, the system must not substitute or hallucinate alternative passages.
- In that scenario, the system generates an explicit grounded notification stating that the specified section was not found in the uploaded document.

---

## 4. Dual Retrieval

When `is_comparative` is `True` and the comparison targets include `"abstract"` and `"results"`, the backend bypasses single-vector retrieval in favor of a dual retrieval strategy:

### Retrieval Execution:
1. **Abstract Pass**:
   - Query: Built from the section's own wording (e.g., `"Abstract study background objectives summary"`), not from the user's conversational prompt.
   - Parameter: `top_k = 3`.
2. **Results Pass**:
   - Query: Built from the results section's own terminology (e.g., `"Results main findings observed prevalence metrics reduction"`), not from the user's conversational prompt.
   - Parameter: `top_k = 3`.

### Merge and Deduplication Pipeline:
1. Combine the retrieved chunk lists from both passes (3 + 3 = 6 potential chunks).
2. Deduplicate chunks by unique `chunk_id` (`id`).
3. Sort all remaining unique chunks by cosine distance in ascending order.
4. Pass the resulting combined list into `assemble_chat_messages` as `<RETRIEVED_CHUNKS>`.

This guarantees that both the Abstract and Results passages are present in the model's prompt context, enabling valid cross-passage in-context synthesis.

---

## 5. Unchanged Paths

All non-comparative chat queries follow the existing, battle-tested execution pipeline:
- **Single Retrieval**: Queries where `is_comparative is False` continue to execute the single `retrieve` call using the existing rewritten `query` with `top_k=5`.
- **Distance Threshold**: The distance cutoff setting (`settings.citation_max_distance = 0.87`) remains active on all retrieved chunks across all pathways.
- **Synthesis Prompt Invariants**: The system prompt (`CHAT_SYSTEM_PROMPT_TEMPLATE`) Section 3 grounding rules remain unchanged.
- **Fallback Sentence**: The immutable fallback contract (`"The uploaded paper does not contain information to answer this question."`) remains unmodified.

---

## 6. Tests to Define

Automated test suites must implement the following test cases in `backend/tests/`:

1. **Dual Retrieval Trigger Test**:
   - Verify that a request classified with `is_comparative=True` and `comparison_targets=["abstract", "results"]` triggers exactly two distinct `retrieve` calls with `top_k=3`.
2. **Single Retrieval Regression Test**:
   - Verify that standard queries (`is_comparative=False`) trigger exactly one `retrieve` call with `top_k=5`.
3. **Missing Section Grounded Handling**:
   - Verify that when an uploaded paper lacks an abstract section, the system outputs the not-found notification rather than substituting ungrounded text.
4. **Chunk Deduplication Test**:
   - Verify that if a chunk is returned by both retrieval passes, duplicate chunk IDs are pruned prior to assembling prompt context.
5. **Fallback Invariance Test**:
   - Verify that ungrounded queries across comparative pathways still strictly return `FALLBACK_GROUNDING_MESSAGE` verbatim.

---

## 7. Evaluation Procedure

To confirm the efficacy of multi-section retrieval against real papers:

1. **Production Paper Ingestion Baseline**:
   - Re-upload the 6-page evaluation paper (`Impactofmasschemotherapyongeohelminthinfections.pdf`) on the target environment.
   - Verify and record its baseline dimensions:
     * Page count: expected **5** pages in Chroma collection.
     * Stored chunk count: expected **21** chunks.
2. **Pre-Change vs. Post-Change Comparison**:
   - Execute the Author Persona query three times before and three times after the implementation:
     `"Does the abstract accurately summarize all the main results and findings reported in the paper?"`
   - Record every raw response.
   - Grade each run:
     * **Grounded**: Cites/quotes statements from both the Abstract and the Results sections.
     * **Fallback**: Returns the standard ungrounded fallback sentence.
