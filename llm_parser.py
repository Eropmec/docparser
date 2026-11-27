#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
LLM-парсер для интеллектуального разбора нормативных документов
"""

from typing import List, Dict
import json
import re


class LLMConditionExtractor:
    """Извлечение условий с помощью LLM"""
    
    def __init__(self, model_path: str, n_ctx: int = 2048, n_threads: int = 4):
        try:
            from llama_cpp import Llama
            self.llm = Llama(
                model_path=model_path,
                n_ctx=n_ctx,
                n_threads=n_threads,
                verbose=False
            )
            self.available = True
        except ImportError:
            self.available = False
            print("llama-cpp-python не установлен - LLM недоступен")
        except Exception as e:
            self.available = False
            print(f"Ошибка загрузки модели: {e}")
    
    def extract_conditions(self, clause_text: str, clause_number: str) -> List[Dict]:
        if not self.available:
            return []
        
        prompt = f"""Ты - эксперт по анализу нормативных документов.
Разбей текст пункта на элементарные условия и следствия.

Пункт {clause_number}:
{clause_text}

Верни JSON:
[
  {{"condition": "текст условия", "consequence": "следствие", "type": "если"}}
]

Отвечай ТОЛЬКО JSON."""

        try:
            response = self.llm(
                prompt, max_tokens=1024, temperature=0.1,
                stop=["\n\n\n"], echo=False
            )
            result_text = response['choices'][0]['text'].strip()
            json_match = re.search(r'\[[\s\S]*\]', result_text)
            if json_match:
                return json.loads(json_match.group())
            return []
        except Exception as e:
            print(f"Ошибка LLM: {e}")
            return []


class HybridParser:
    """Гибридный парсер: regex + LLM"""
    
    def __init__(self, use_llm: bool = False, model_path: str = None):
        self.use_llm = use_llm
        self.llm_extractor = None
        if use_llm and model_path:
            self.llm_extractor = LLMConditionExtractor(model_path)
    
    def parse_clause(self, clause_number: str, clause_text: str) -> List[Dict]:
        if self.use_llm and self.llm_extractor and self.llm_extractor.available:
            conditions = self.llm_extractor.extract_conditions(clause_text, clause_number)
            if conditions:
                return conditions
        return self._regex_parse(clause_text, clause_number)
    
    def _regex_parse(self, text: str, clause_number: str) -> List[Dict]:
        conditions = []
        pattern = r'(?:если|при|в случае|когда)\s+([^,]+)(?:,\s*то)?\s*([^.]*)'
        matches = re.finditer(pattern, text, re.IGNORECASE)
        
        for i, match in enumerate(matches):
            condition_text = match.group(1).strip()
            consequence_text = match.group(2).strip()
            if condition_text:
                conditions.append({
                    "condition": condition_text,
                    "consequence": consequence_text,
                    "type": "если"
                })
        
        if not conditions:
            conditions.append({
                "condition": text,
                "consequence": "",
                "type": "требование"
            })
        return conditions