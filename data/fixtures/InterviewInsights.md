# Applied Coding

April 2, 2026 4:00–4:45 PM EDT

practical, real-world exercise: in a real workflow environment, quickly understand the requirements, write/modify a piece of runnable code, and clearly explain why you did it this way.  
Requires Python 3.12+ / uv, Node.js v18+, and an IDE,  
By default, candidates are expected to quickly enter a real development environment.

# 1 David Brinda

David \- full-stack generalist turned document AI manager, evaluates engineering feel, AI judgment, and communication style.  
David \- Supio's Document Intelligence direction, responsible for structured extraction at 1M+ pages/day, evaluation framework, HITL feedback, fine-tuning pipeline, prompt design / CoT / RAG;  
startup full-stack generalist, [Node.js](http://Node.js), React/Next.js, databases, AWS, performance tuning.

## 1.1 Detailed Background

AI Engineering Manager \- Document Intelligence   
November 2025 \- Present (5 months)   
\- Lead AI/ML team responsible for extracting structured data from over 1 million pages per day   
\- Design/Build evaluation framework that produced metrics on model performance   
\- Design HITL feedback processes to reinforce models and detect issues   
\- Build tools and pipeline for fine tuning models \- Prompt design, CoT, fine tuning, RAG, etc  
\- Collaborate with other teams to understand how they can benefit from automation   
\- Plan project roadmaps   
\- Interview candidates, design interview questions, and screen resumes 

# 2 Role Focus

production-level software engineering, large-scale document AI feature.  
raw PDFs   
→   
structured insights, RAG / agentic systems, prototype to production, evaluation of accuracy/latency/reliability, classification / clustering / semantic matching, backend APIs / model serving / cloud infra / monitoring

## 2.1 Profile

Quickly understand an unfamiliar small task / small code environment and move it forward;  
Not only able to call APIs, but also understand the product and quality issues behind document AI / RAG / evaluation / HITL;  
Drive features end-to-end in a small team

* Have full-stack / backend engineering ability;  
* Understand prompt engineering / CoT / fine-tune / eval;  
* Have business sense / user sense;  
* Interviews mix debug / code / AI reasoning / realistic workflow

## 2.2 Key Focus

First layer: engineering fundamentals  
Quickly locate problems, break down tasks, write clean code, and get things running.

Second layer: "reliability awareness" for AI features

Third layer: product sense  
Help paralegals / attorneys work faster, more accurately, and more verifiably.

- Organize materials, retrieve hundreds of pages of medical records, verify medical code/expense/treatment details;  
- Must not make users lose trust; must have fallback/human review/evidence-backed output.

## 2.3 Positioning Fit

See StroyBanks for details

# 3 Question Examples

## 3.1 Fullstack

* Small repo / zip, get it running, fix bugs, add a small feature;  
* Input data, do parsing / transformation / scoring / evaluation;  
* LLM / summary / extraction, write code to implement or explain the implementation;  
* "Why design it this way", "What if the data volume is larger", "How to verify whether the result is correct".

See VO interview experience for details:  
One-hour debugging. The interviewer emails over a source code repo; run it locally yourself and fix the issues  
Need some familiarity with how to use AI APIs  
A chat interface  
bug1: console shows api key invalid. Reason: wrong api key  
bug2: after sending a request in the chat box, the rendered returned message is empty. Reason: the returned text is in the token field, but local code reads the text field  
feature1: add a clear button that, when clicked, clears message history and context and reinitializes. There is an existing action in the store that can be called directly  
feature2: add a stop button to terminate streaming while OpenAI is streaming back the response, similar to ChatGPT's stop button (small square icon). Related to state management  
Although this kind of interview is closer to real work, if you are unfamiliar with the tech stack it still takes some time to adapt and understand, and for bug2 (API return data type differs from what local code expects), you really need to adjust your thinking to realize the issue.  
There should have been other feature requirements later, but there was no time.

## 3.2 Document Intelligence

Input long documents, messy documents, cross-source documents

User-verifiable and traceable.

For legal/medical files, many fields can be divided into two types:  
deterministic facts (code, age, expense, dates)

- exact/normalized comparison

open-ended summaries (case summary, medical summary, chronology narrative)

-  rubric / outline / semantic similarity / fact coverage / contradiction detection / HITL review 

30 minutes, asking how to compare an AI-generated medical summary with a human-written one and score their difference. For example, given a medical file, a human writes a summary with title, summary, time, category, etc., and AI writes one too. How to calculate their difference.  
“How would you evaluate AI-generated medical summaries against human-written summaries?”

Step 1: split output fields into deterministic vs open-ended.

* deterministic: title category date age code expense provider, etc.  
   → normalization \+ exact match / tolerance-based match  
* open-ended: summary / chronology / treatment narrative  
   → Cannot use a single metric to judge

Step 2: evaluate open-ended summaries across multiple dimensions.

* coverage: key fact coverage  
* faithfulness / grounding: supported by source evidence  
* consistency: does not conflict with structured fields  
* semantic similarity: close to the reference in meaning  
* actionability: useful enough to help paralegal review / demand drafting

Step 3: in technical implementation, combine multiple methods instead of relying on a single point.

* embeddings \+ cosine similarity；  
* fact extraction / checklist-based validation；  
* contradiction / missing-fact checks；  
* LLM-as-judge based on a rubric or outline;  
* Output failure categories: missing date / wrong code / unsupported claim / omitted treatment, etc.

Step 4: do slice-based evaluation.  
Slice by document type, injury type, summary length, OCR quality, provider source; average score is not meaningful.  
Step 5: HITL.  
human review  \- "verify and correct" instead of "rewrite the whole text".  
   
Help paralegals discover differences faster, rather than replacing them  
"How does this help paralegals / attorneys review faster, reduce omissions, and improve trust."

# 4 Preparation

## 4.1 Environment

* Python 3.12+  
* uv 0.9.16+  
* Node.js v18+  
* Git / clone repo  
* IDE  
* Teams

## 4.2 Question Types

A. Unfamiliar repo / script startup \+ bug fixing  
 Practice:

* Read README  
* Create env  
* Run tests / run main  
* Inspect traceback / console  
* Fix schema mismatch / field name mismatch / config/env bug

B. Small data task

* Read JSON/CSV/text  
* Normalize fields  
* Extract deterministic fields  
* Build a scoring / comparison function  
* Output structured JSON

C. LLM workflow task

* Write prompts  
* Design JSON schema  
* Add validation  
* Handle bad outputs  
* Explain how to eval

## 4.3 BQ

Review resume \- 

* What is the background  
* What is the user problem  
* What exactly did you do  
* What was the hardest tradeoff  
* How did you eval  
* What was the result  
* What would you change if you did it again

# 5 Pace

1. First restate the requirements  
2. Get it running first, then modify  
3. Talk while working  
* I'll first inspect the entry point  
* I'll first confirm the data shape  
* Here I suspect a schema mismatch  
* Here I'll first make the minimal fix, then see whether refactoring is needed  
4. Proactively discuss tradeoffs  
* Here I'll first use a simple implementation to ensure correctness  
* If the data volume is larger, I would switch to streaming / batching / indexing  
* If this were production, I would add logging / tests / validation  
5. If you encounter a repeated question, mention it immediately, otherwise you may be suspected of not being honest.

# 6 Preparation Focus

For each question, think about

1. The business scenario, and how to view the problem from the customer and user perspective,  
2. What the impact is on users and business outcomes after debugging / shipping the feature,  
3. Why do it this way, tradeoff considerations

Once you get the problem, communicate clearly

1. Quickly read the repo first, configure the environment requirements, get the whole project running, then move to the next step  
2. Clarify the requirements, quickly locate the problem, and identify the key point,  
3. Break down tasks, quickly read the code, explain your thought process, and validate it with the interviewer,  
4. Then write code and debug,  
5. Verify the effect, explain results and tradeoffs, and think from the business side

## 6.1 Document Intelligence

Focus on downloading data to get raw data, reading data, processing data formats, optimizing, and thinking about how to handle very large individual data size and very large data volume.

Development practice

1. How to parse a single raw PDF document into Structured Information and then Structured Insights  
2. For different document categories, such as legal, medical, bills, treatment, how to process, distinguish, and integrate them  
3. For different file types, such as PDFs, txts, mixed media, etc., how to process, distinguish, and integrate them  
4. How to process a single very large file, such as thousands-of-page PDFs, long mixed media, etc.  
5. How to End-to-End Evaluate Document Intelligence with the above methods, what metrics and scores are used, how to balance precision and recall and other accuracy metrics, processing speed latency, performance tradeoffs, and ensure reliability + speed at scale (100k MAU setting)  
6. How to handle data preprocessing and post-processing on the document intelligence side, and upgrade from prototype to production level

## 6.2 Applied AI ML LLM

After the above data processing, use an LLM to do something: how to design prompts, how to optimize, how to evaluate, what each parameter specifically means, and result comparison must be fast and evidence-backed

Development practice

1. Use extracted structured information to build an ML Pipeline \- Classification, cluerting, semantic matching  
2. Fine-tune LLMs, or do system-level optimization for the scenario (not the main focus, but need to understand)  
3. RAG design details (vector store, retrieve)  
- One thought: can important embedding dimensions be designed like attention? Since human expertise is very valuable in legal scenarios, can it be transferred into RAG design, and how to avoid returning irrelevant information and only return useful content  
- Also, for very long PDFs or other documents, how to let the LLM search faster without losing focus  
4. CoT implementation details, how to design prompts  
5. Do document summarization and case analysis, with evidence-backed indices (grounding, citation, hallucination control, evidence traceability...)  
6. How to specifically design a HITL Human In The Loop system  
7. How to End-to-End Evaluate Document Intelligence with the above methods, what metrics and scores are used, how to balance precision and recall and other accuracy metrics, processing speed latency, performance tradeoffs, and ensure reliability + speed at scale (100k MAU setting)  
- Comparison of deterministic facts and comparison of AI-generated open-ended summaries  
8. How to upgrade the above systems from prototype to production and integrate them into the full-stack platform

## 6.3 Software Fullstack

Fullstack must be fast; there are several bugs and features, and if it doesn't run you fail

Trace the chain UI \-\> handler \-\> store/state \-\> API call \-\> server/client wrapper \-\> response parser \-\> render

Development practice

1. Proficient in Python (3.12+), familiar with TypeScript syntax, [Node.js](http://Node.js) (v18+), UV (0.9.16+), React, [Next.js](http://Next.js), GitHub operations, xxx and other full-stack required skills, and know how to quickly understand repo structure, quickly create env dependencies, get it running, debug, and ship new features  
2. Large-Scale, how to handle data ingestion, pre-processing, post-preocessing, etc. when 100k PDFs are uploaded per day, and pay attention to very high backend concurrency; peak daily load may reach millions or tens of millions of PDF pages  
3. Understand backend API interface specs, and be able to quickly read, modify, and debug them (database, backend, frontend), examples  
- bug1: console shows api key invalid. Reason: wrong api key  
- bug2: after sending a request in the chat box, the rendered returned message is empty. Reason: the returned text is in the token field, but local code reads the text field  
4. Quickly ship features, quickly finish frontend and backend, examples  
- feature1: add a clear button that, when clicked, clears message history and context and reinitializes. There is an existing action in the store that can be called directly  
- feature2: add a stop button to terminate streaming while OpenAI is streaming back the response, similar to ChatGPT's stop button (small square icon). Related to state management  
5. How to do model serving specifically, including local data processing, how to deploy trained ML Models and incoming LLM API interfaces, and how to ship them as production-level platform AI features  
6. Large-scale production cloud infrastructure, know which tech stack to use and why to use the AWS full suite and containerized environments  
7. System Monitoring production-level code, production reliability at scale, handling metrics/logging, health checks, retries/backoff, testing, documentation, etc., and focusing on accuracy / latency / reliability / observability / failure isolation in 100k MAU settings
