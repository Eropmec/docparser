#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Гибридный парсер нормативных документов (Regex + LLM + Умная очистка и Скоринг)
"""

from typing import List, Dict
import re
import json


def clean_ocr_text(text: str) -> str:
    """Очистка текста от артефактов PDF (переносы, рассыпанные буквы)"""
    text = re.sub(r'-\s*\n\s*', '', text)
    
    def merge_spaced(match):
        word = match.group(0).replace(' ', '')
        return word if len(word) >= 3 else match.group(0)
    
    text = re.sub(r'\b(?:[А-Яа-яЁё]\s+){2,14}[А-Яа-яЁё]\b', merge_spaced, text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text


def score_requirement(text: str) -> Dict:
    """Весовой скоринг текста для определения, является ли он жестким требованием"""
    text_lower = text.lower()
    weights = {
        "restriction": 1.0, "modal_strong": 0.8, "normative": 0.6,
        "condition": 0.3, "modal_weak": -0.2, "meta_text": -0.9
    }
    patterns = {
        "restriction": r'\b(не допускается|запрещено|исключается|не разрешается)\b',
        "modal_strong": r'\b(должен|должна|должно|обязан|требуется|необходимо)\b',
        "normative": r'\b(устанавливается|определяется|принимается|выполняется)\b',
        "condition": r'\b(при|если|в случае|когда)\b',
        "modal_weak": r'\b(рекомендуется|может|желательно|целесообразно)\b',
        "meta_text": r'\b(см\.|приложение|в соответствии с|согласно)\b'
    }
    
    score = 0.0
    found_markers = []
    for marker, pattern in patterns.items():
        if re.search(pattern, text_lower):
            score += weights[marker]
            found_markers.append(marker)
            
    score = max(0.0, min(1.5, score))
    return {"score": round(score, 2), "is_requirement": score >= 0.5, "markers": found_markers}


class LLMConditionExtractor:
    def __init__(self, model_path: str, n_ctx: int = 2048, n_threads: int = 4):
        self.available = False
        self.llm = None
        try:
            import llama_cpp
            self.llm = llama_cpp.Llama(model_path=model_path, n_ctx=n_ctx, n_threads=n_threads, verbose=False)
            self.available = True
        except ImportError:
            print("ВНИМАНИЕ: llama-cpp-python не установлен. Используется продвинутый Regex-парсер.")
        except Exception as e:
            print(f"Ошибка загрузки модели: {e}")
    
    def extract_conditions(self, clause_text: str, clause_number: str) -> List[Dict]:
        if not self.available or self.llm is None:
            return []
        prompt = f"""Ты - эксперт по анализу нормативных документов. Разбей текст пункта на элементарные условия и следствия.
Пункт {clause_number}:\n{clause_text}\n
Верни JSON: [ {{"condition": "текст условия", "consequence": "следствие", "type": "если"}} ]
Отвечай ТОЛЬКО JSON."""
        try:
            response = self.llm(prompt, max_tokens=1024, temperature=0.1, stop=["\n\n\n"], echo=False)
            result_text = response['choices'][0]['text'].strip()
            json_match = re.search(r'\[[\s\S]*\]', result_text)
            return json.loads(json_match.group()) if json_match else []
        except Exception as e:
            print(f"Ошибка LLM: {e}")
            return []


class ConditionConsolidator:
    """Интеллектуальный поиск и объединение смысловых дубликатов"""
    def __init__(self, llm_extractor):
        self.llm_extractor = llm_extractor

    def _jaccard_similarity(self, text1: str, text2: str) -> float:
        words1 = set(re.findall(r'\w+', text1.lower()))
        words2 = set(re.findall(r'\w+', text2.lower()))
        stop_words = {'и', 'в', 'не', 'на', 'с', 'по', 'для', 'от', 'до', 'из', 'же', 'бы', 'ли', 'или'}
        words1 = {w for w in words1 if len(w) > 2 and w not in stop_words}
        words2 = {w for w in words2 if len(w) > 2 and w not in stop_words}
        if not words1 or not words2: return 0.0
        return len(words1.intersection(words2)) / len(words1.union(words2))

    def find_and_merge_duplicates(self, conditions_list: List[Dict], similarity_threshold: float = 0.25) -> List[Dict]:
        merged_results = []
        processed_indices = set()
        
        for i, cond1 in enumerate(conditions_list):
            if i in processed_indices: continue
            text1 = f"{cond1.get('condition', '')} {cond1.get('consequence', '')}"
            current_group = [cond1]
            
            candidates = []
            for j, cond2 in enumerate(conditions_list):
                if i == j or j in processed_indices: continue
                text2 = f"{cond2.get('condition', '')} {cond2.get('consequence', '')}"
                sim = self._jaccard_similarity(text1, text2)
                if sim >= similarity_threshold:
                    candidates.append((j, cond2, sim))
            
            if candidates and self.llm_extractor and self.llm_extractor.available:
                for j, cond2, sim in candidates:
                    text2 = f"{cond2.get('condition', '')} {cond2.get('consequence', '')}"
                    merge_result = self._ask_llm_to_merge(text1, text2)
                    if merge_result.get("are_similar"):
                        current_group.append(cond2)
                        processed_indices.add(j)
                        text1 = merge_result.get("merged_text", text1)
                        cond1['condition'] = text1
                        cond1['consequence'] = ""
                        cond1['merged_from'] = [c.get('id') for c in current_group]
                        cond1['merge_reason'] = merge_result.get("reason", "Смысловое совпадение")
            else:
                for j, cond2, sim in candidates:
                    if sim >= 0.4:
                        current_group.append(cond2)
                        processed_indices.add(j)
                        cond1['merged_from'] = [c.get('id') for c in current_group]
                        cond1['merge_reason'] = "Высокое текстовое сходство (LLM недоступен)"

            processed_indices.add(i)
            merged_results.append(cond1)
        return merged_results

    def _ask_llm_to_merge(self, text1: str, text2: str) -> Dict:
        prompt = f"""Сравни два требования на смысловую идентичность.
1: "{text1}"
2: "{text2}"
Если они означают одно и то же или дополняют друг друга, объедини их в одно четкое требование. Если о разных вещах — укажи это.
Верни ТОЛЬКО JSON: {{"are_similar": true/false, "merged_text": "объединенный текст или ''", "reason": "обоснование"}}"""
        try:
            response = self.llm_extractor.llm(prompt, max_tokens=512, temperature=0.0, stop=["\n\n\n"], echo=False)
            json_match = re.search(r'\{[\s\S]*\}', response['choices'][0]['text'].strip())
            return json.loads(json_match.group()) if json_match else {"are_similar": False}
        except Exception:
            return {"are_similar": False}


class HybridParser:
    def __init__(self, use_llm: bool = False, model_path: str = None):
        self.use_llm = use_llm
        self.llm_extractor = None
        if use_llm and model_path:
            self.llm_extractor = LLMConditionExtractor(model_path)
    
    def parse_clause(self, clause_number: str, clause_text: str) -> List[Dict]:
        clean_text = clean_ocr_text(clause_text)
        if self.use_llm and self.llm_extractor and self.llm_extractor.available:
            conditions = self.llm_extractor.extract_conditions(clean_text, clause_number)
            if conditions:
                for cond in conditions:
                    scoring = score_requirement(cond.get("condition", "") + " " + cond.get("consequence", ""))
                    cond.update({"score": scoring["score"], "is_requirement": scoring["is_requirement"], "markers": scoring["markers"]})
                return conditions
        return self._regex_parse(clean_text, clause_number)
    
    def _regex_parse(self, text: str, clause_number: str) -> List[Dict]:
        conditions = []
        pattern = r'(?:если|при|в случае|когда)\s+([^,;]+)(?:,\s*(?:то)?)?\s*([^.]*)'
        for match in re.finditer(pattern, text, re.IGNORECASE):
            cond_text, cons_text = match.group(1).strip(), match.group(2).strip()
            if cond_text:
                full_text = f"{cond_text} {cons_text}"
                scoring = score_requirement(full_text)
                conditions.append({"condition": cond_text, "consequence": cons_text, "type": "условие", 
                                   "score": scoring["score"], "is_requirement": scoring["is_requirement"], "markers": scoring["markers"]})
        if not conditions:
            scoring = score_requirement(text)
            conditions.append({"condition": text, "consequence": "", "type": "прямое_требование", 
                               "score": scoring["score"], "is_requirement": scoring["is_requirement"], "markers": scoring["markers"]})
        return conditions
