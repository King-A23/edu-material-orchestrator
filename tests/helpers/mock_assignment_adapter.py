from __future__ import annotations

import json
import re
import sys


def _is_chinese(text: str) -> bool:
    return bool(re.search(r"[\u3400-\u9fff]", text))


def main() -> int:
    payload = json.loads(sys.stdin.read())
    task_type = payload["task_type"]

    if task_type == "question_analysis":
        question_original = payload["input"]["question_original"]
        source_language = payload["input"].get("source_language")
        translation = None if source_language == "zh" or _is_chinese(question_original) else f"中文翻译：{question_original}"
        response = {
            "question_translation_zh": translation,
            "reference_answer": "Mock reference answer.",
            "solution_approach": "Identify the core requirement and apply the relevant rule.",
            "detailed_steps": [
                "Read the question carefully.",
                "Extract the relevant conditions from the source text.",
                "Apply the matching concept or formula to reach the result.",
            ],
            "knowledge_points": ["题意理解", "规则应用"],
            "inference_notes": [],
            "status": "ok",
        }
        print(json.dumps(response, ensure_ascii=False))
        return 0

    if task_type == "chapter_outline":
        response = {
            "content_markdown": (
                "1. 识别题目条件与目标。\n"
                "2. 选择合适的公式、定义或推理方法。\n"
                "3. 检查答案表达是否完整。"
            )
        }
        print(json.dumps(response, ensure_ascii=False))
        return 0

    if task_type == "quiz_generation":
        selected_references = payload["input"].get("selected_references", [])
        questions = []
        for index, reference in enumerate(selected_references[:2], start=1):
            image_reference_ids = [
                image_ref["image_id"]
                for image_ref in reference.get("image_refs", [])[:1]
            ]
            questions.append(
                {
                    "question_type": "short_answer",
                    "stem_markdown": f"请根据参考资料回答第 {index} 题：{reference['title']}",
                    "options": [],
                    "answer_markdown": f"Mock answer for {reference['reference_id']}.",
                    "explanation_markdown": "先概括核心概念，再给出简洁结论。",
                    "source_reference_ids": [reference["reference_id"]],
                    "image_reference_ids": image_reference_ids,
                    "review_notes": [],
                }
            )
        response = {
            "title": "Mock Quiz",
            "instructions_markdown": "请独立完成以下测验。",
            "questions": questions or [
                {
                    "question_type": "short_answer",
                    "stem_markdown": "Mock fallback question.",
                    "options": [],
                    "answer_markdown": "Mock fallback answer.",
                    "explanation_markdown": "Mock fallback explanation.",
                    "source_reference_ids": [],
                    "image_reference_ids": [],
                    "review_notes": ["No selected references were available in the mock adapter."],
                }
            ],
        }
        print(json.dumps(response, ensure_ascii=False))
        return 0

    if task_type == "submission_grading":
        student_answer = str(payload["input"].get("student_answer") or "")
        reference_answer = str(payload["input"].get("reference_answer") or "")
        rubric_criteria = payload["input"].get("rubric_criteria", [])
        max_score = float(payload["input"].get("max_score") or 10)
        answer_lower = student_answer.lower()

        if not student_answer.strip():
            response = {
                "score": 0.0,
                "max_score": max_score,
                "verdict": "needs_review",
                "matched_steps": [],
                "missing_steps": rubric_criteria[:2] or ["未作答"],
                "deductions": ["学生未提供答案。"],
                "feedback_markdown": "未检测到有效作答内容。",
                "review_notes": ["学生答案为空。"],
            }
        elif "not sure" in answer_lower or "不确定" in answer_lower:
            response = {
                "score": round(max_score * 0.3, 2),
                "max_score": max_score,
                "verdict": "partial",
                "matched_steps": [],
                "missing_steps": rubric_criteria[:2] or ["缺少明确结论"],
                "deductions": ["答案缺少明确结论。"],
                "feedback_markdown": "答案过于笼统，未形成可判定的完整结论。",
                "review_notes": [],
            }
        else:
            response = {
                "score": max_score,
                "max_score": max_score,
                "verdict": "correct",
                "matched_steps": [rubric_criteria[0]] if rubric_criteria else [f"给出正确结论：{reference_answer}"],
                "missing_steps": [],
                "deductions": [],
                "feedback_markdown": "答案与参考答案语义基本一致。",
                "review_notes": [],
            }
        print(json.dumps(response, ensure_ascii=False))
        return 0

    if task_type == "question_variants":
        seed_questions = payload["input"].get("seed_questions", [])
        count = int(payload["input"].get("count") or 3)
        questions = []
        for index in range(count):
            seed = seed_questions[index % len(seed_questions)] if seed_questions else {}
            question_type = seed.get("question_type", "short_answer")
            source_question_record_id = seed.get("question_record_id", f"seed-{index + 1}")
            stem = seed.get("stem_markdown", "Mock seed question.")
            questions.append(
                {
                    "question_type": question_type,
                    "stem_markdown": f"变式题 {index + 1}：请在原题基础上完成训练。原题：{stem}",
                    "answer_markdown": f"Mock variant answer {index + 1}.",
                    "explanation_markdown": "先识别原题考点，再完成条件变化后的求解。",
                    "source_question_record_ids": [source_question_record_id],
                    "review_notes": [],
                }
            )
        response = {
            "title": "Mock Variants",
            "instructions_markdown": "请完成以下变式训练。",
            "questions": questions,
        }
        print(json.dumps(response, ensure_ascii=False))
        return 0

    print(json.dumps({"error": f"unsupported task_type: {task_type}"}, ensure_ascii=False))
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
