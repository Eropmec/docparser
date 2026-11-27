#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Система разбора нормативных документов - GUI версия с LLM
"""

import tkinter as tk
from tkinter import ttk, messagebox, filedialog, scrolledtext
import re
import json
from typing import List, Dict, Set
from dataclasses import dataclass, field, asdict
from llm_parser import HybridParser


@dataclass
class Condition:
    id: str
    text: str
    clause_id: str
    depends_on: List[str] = field(default_factory=list)


@dataclass
class Clause:
    number: str
    text: str
    conditions: List[Condition] = field(default_factory=list)
    references: List[str] = field(default_factory=list)


@dataclass
class Consequence:
    id: str
    text: str
    required_conditions: List[str]
    source_clauses: List[str] = field(default_factory=list)


class DocumentParser:
    def __init__(self, hybrid_parser: HybridParser = None):
        self.clauses: Dict[str, Clause] = {}
        self.conditions: Dict[str, Condition] = {}
        self.consequences: Dict[str, Consequence] = {}
        self.hybrid_parser = hybrid_parser or HybridParser()
        
    def parse_text(self, text: str) -> None:
        clause_pattern = r'(\d+(?:\.\d+)*)\s+([^\n]+(?:\n(?!\d+\.|\d+\.\d+)[^\n]+)*)'
        matches = re.finditer(clause_pattern, text)
        for match in matches:
            number = match.group(1)
            clause_text = match.group(2).strip()
            self._parse_clause(number, clause_text)
    
    def _parse_clause(self, number: str, text: str) -> None:
        clause = Clause(number=number, text=text)
        parsed_conditions = self.hybrid_parser.parse_clause(number, text)
        
        for i, cond_data in enumerate(parsed_conditions):
            condition_text = cond_data.get("condition", "").strip()
            consequence_text = cond_data.get("consequence", "").strip()
            if not condition_text:
                continue
            
            cond_id = f"{number}.{i+1}"
            condition = Condition(id=cond_id, text=condition_text, clause_id=number)
            clause.conditions.append(condition)
            self.conditions[cond_id] = condition
            
            if consequence_text:
                cons_id = f"cons_{number}_{i+1}"
                consequence = Consequence(
                    id=cons_id, text=consequence_text,
                    required_conditions=[cond_id], source_clauses=[number]
                )
                self.consequences[cons_id] = consequence
        
        if not clause.conditions:
            cond_id = f"{number}.1"
            condition = Condition(id=cond_id, text=text, clause_id=number)
            clause.conditions.append(condition)
            self.conditions[cond_id] = condition
        
        ref_pattern = r'(?:см\.\s*|согласно\s*|в соответствии с\s*|пункт\s*)(\d+(?:\.\d+)*)'
        refs = re.findall(ref_pattern, text, re.IGNORECASE)
        clause.references = list(set(refs))
        self.clauses[number] = clause
    
    def add_manual_consequence(self, text: str, required_conditions: List[str], 
                               source_clauses: List[str] = None) -> str:
        cons_id = f"manual_{len(self.consequences) + 1}"
        consequence = Consequence(
            id=cons_id, text=text, required_conditions=required_conditions,
            source_clauses=source_clauses or []
        )
        self.consequences[cons_id] = consequence
        return cons_id
    
    def get_consequences_for_conditions(self, active_conditions: List[str]) -> List[Consequence]:
        active_set = set(active_conditions)
        return [c for c in self.consequences.values() 
                if all(cid in active_set for cid in c.required_conditions)]
    
    def to_dict(self) -> dict:
        return {
            'conditions': {k: asdict(v) for k, v in self.conditions.items()},
            'clauses': {k: asdict(v) for k, v in self.clauses.items()},
            'consequences': {k: asdict(v) for k, v in self.consequences.items()}
        }
    
    def from_dict(self, data: dict) -> None:
        self.conditions = {k: Condition(**v) for k, v in data['conditions'].items()}
        self.clauses = {k: Clause(**v) for k, v in data['clauses'].items()}
        self.consequences = {k: Consequence(**v) for k, v in data['consequences'].items()}


class ComplianceChecker:
    def __init__(self, parser: DocumentParser):
        self.parser = parser
        self.active_conditions: Set[str] = set()
    
    def activate_condition(self, condition_id: str) -> None:
        if condition_id in self.parser.conditions:
            self.active_conditions.add(condition_id)
    
    def deactivate_condition(self, condition_id: str) -> None:
        self.active_conditions.discard(condition_id)
    
    def get_active_consequences(self) -> List[Consequence]:
        return self.parser.get_consequences_for_conditions(list(self.active_conditions))
    
    def check_compliance(self) -> dict:
        total = len(self.parser.conditions)
        active = len(self.active_conditions)
        consequences = self.get_active_consequences()
        return {
            'total_conditions': total,
            'active_conditions': active,
            'active_consequences': len(consequences),
            'coverage': (active / total * 100) if total > 0 else 0
        }


class LLMSettingsDialog(tk.Toplevel):
    def __init__(self, parent, current_settings: dict):
        super().__init__(parent)
        self.result = None
        self.title("Настройки LLM")
        self.geometry("500x300")
        self.resizable(False, False)
        
        self.use_llm_var = tk.BooleanVar(value=current_settings.get('use_llm', False))
        ttk.Checkbutton(self, text="Использовать LLM для разбора", 
                       variable=self.use_llm_var).pack(pady=10, anchor='w', padx=10)
        
        ttk.Label(self, text="Путь к GGUF модели:").pack(pady=5, anchor='w', padx=10)
        model_frame = ttk.Frame(self)
        model_frame.pack(fill='x', padx=10, pady=5)
        
        self.model_path_var = tk.StringVar(value=current_settings.get('model_path', ''))
        ttk.Entry(model_frame, textvariable=self.model_path_var).pack(side='left', fill='x', expand=True)
        ttk.Button(model_frame, text="Обзор...", command=self.browse_model).pack(side='right', padx=5)
        
        ttk.Label(self, text="Размер контекста:").pack(pady=5, anchor='w', padx=10)
        self.n_ctx_var = tk.IntVar(value=current_settings.get('n_ctx', 2048))
        ttk.Spinbox(self, from_=512, to=8192, textvariable=self.n_ctx_var).pack(padx=10, fill='x')
        
        ttk.Label(self, text="Количество потоков:").pack(pady=5, anchor='w', padx=10)
        self.n_threads_var = tk.IntVar(value=current_settings.get('n_threads', 4))
        ttk.Spinbox(self, from_=1, to=16, textvariable=self.n_threads_var).pack(padx=10, fill='x')
        
        button_frame = ttk.Frame(self)
        button_frame.pack(fill='x', padx=10, pady=20)
        ttk.Button(button_frame, text="Сохранить", command=self.save).pack(side='right', padx=5)
        ttk.Button(button_frame, text="Отмена", command=self.destroy).pack(side='right', padx=5)
    
    def browse_model(self):
        filename = filedialog.askopenfilename(
            title="Выберите GGUF модель",
            filetypes=[("GGUF файлы", "*.gguf"), ("Все файлы", "*.*")]
        )
        if filename:
            self.model_path_var.set(filename)
    
    def save(self):
        self.result = {
            'use_llm': self.use_llm_var.get(),
            'model_path': self.model_path_var.get(),
            'n_ctx': self.n_ctx_var.get(),
            'n_threads': self.n_threads_var.get()
        }
        self.destroy()


class AddConsequenceDialog(tk.Toplevel):
    def __init__(self, parent, parser: DocumentParser):
        super().__init__(parent)
        self.parser = parser
        self.result = None
        self.title("Добавить следствие")
        self.geometry("500x400")
        self.resizable(False, False)
        
        ttk.Label(self, text="Текст следствия:").pack(pady=5, anchor='w', padx=10)
        self.text_entry = scrolledtext.ScrolledText(self, height=4, width=55)
        self.text_entry.pack(pady=5, padx=10)
        
        ttk.Label(self, text="Выберите требуемые условия:").pack(pady=5, anchor='w', padx=10)
        
        conditions_frame = ttk.Frame(self)
        conditions_frame.pack(fill='both', expand=True, padx=10, pady=5)
        
        canvas = tk.Canvas(conditions_frame)
        scrollbar = ttk.Scrollbar(conditions_frame, orient="vertical", command=canvas.yview)
        self.scrollable_frame = tk.Frame(canvas)
        
        self.scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        
        canvas.create_window((0, 0), window=self.scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        
        self.condition_vars = {}
        for cond_id, condition in self.parser.conditions.items():
            var = tk.BooleanVar()
            cb = tk.Checkbutton(self.scrollable_frame, 
                               text=f"{cond_id}: {condition.text[:50]}...", 
                               variable=var, anchor='w')
            cb.pack(fill='x', padx=5, pady=2)
            self.condition_vars[cond_id] = var
        
        button_frame = ttk.Frame(self)
        button_frame.pack(fill='x', padx=10, pady=10)
        ttk.Button(button_frame, text="Добавить", command=self.on_add).pack(side='right', padx=5)
        ttk.Button(button_frame, text="Отмена", command=self.destroy).pack(side='right', padx=5)
    
    def on_add(self):
        text = self.text_entry.get("1.0", tk.END).strip()
        if not text:
            messagebox.showwarning("Предупреждение", "Введите текст следствия")
            return
        selected = [cid for cid, var in self.condition_vars.items() if var.get()]
        if not selected:
            messagebox.showwarning("Предупреждение", "Выберите хотя бы одно условие")
            return
        self.result = {'text': text, 'conditions': selected}
        self.destroy()


class DocumentParserApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Система разбора нормативных документов")
        self.root.geometry("1200x700")
        
        self.llm_settings = {'use_llm': False, 'model_path': '', 'n_ctx': 2048, 'n_threads': 4}
        self.hybrid_parser = HybridParser()
        self.parser = DocumentParser(self.hybrid_parser)
        self.checker = ComplianceChecker(self.parser)
        
        self.create_menu()
        self.create_widgets()
        self.load_sample()
    
    def create_menu(self):
        menubar = tk.Menu(self.root)
        self.root.config(menu=menubar)
        
        file_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Файл", menu=file_menu)
        file_menu.add_command(label="Открыть документ...", command=self.open_document)
        file_menu.add_command(label="Сохранить проект...", command=self.save_project)
        file_menu.add_command(label="Загрузить проект...", command=self.load_project)
        file_menu.add_separator()
        file_menu.add_command(label="Выход", command=self.root.quit)
        
        settings_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Настройки", menu=settings_menu)
        settings_menu.add_command(label="Настройки LLM...", command=self.open_llm_settings)
        
        action_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Действия", menu=action_menu)
        action_menu.add_command(label="Добавить следствие...", command=self.add_consequence)
        action_menu.add_command(label="Активировать все", command=self.activate_all)
        action_menu.add_command(label="Деактивировать все", command=self.deactivate_all)
        action_menu.add_command(label="Обновить", command=self.update_display)
        
        help_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Справка", menu=help_menu)
        help_menu.add_command(label="О программе", command=self.show_about)
    
    def create_widgets(self):
        main_frame = ttk.PanedWindow(self.root, orient='horizontal')
        main_frame.pack(fill='both', expand=True, padx=5, pady=5)
        
        left_frame = ttk.Frame(main_frame)
        main_frame.add(left_frame, weight=1)
        
        ttk.Label(left_frame, text="Условия документа", 
                 font=('Arial', 12, 'bold')).pack(pady=5)
        
        self.llm_status_label = ttk.Label(left_frame, text="LLM: выключен", 
                                         foreground='gray', font=('Arial', 9))
        self.llm_status_label.pack(pady=2)
        
        search_frame = ttk.Frame(left_frame)
        search_frame.pack(fill='x', padx=5, pady=5)
        ttk.Label(search_frame, text="Поиск:").pack(side='left')
        self.search_var = tk.StringVar()
        self.search_var.trace('w', self.on_search)
        ttk.Entry(search_frame, textvariable=self.search_var).pack(
            side='left', fill='x', expand=True, padx=5)
        
        conditions_frame = ttk.Frame(left_frame)
        conditions_frame.pack(fill='both', expand=True, padx=5, pady=5)
        
        canvas = tk.Canvas(conditions_frame)
        scrollbar = ttk.Scrollbar(conditions_frame, orient="vertical", command=canvas.yview)
        self.conditions_canvas_frame = tk.Frame(canvas)
        
        self.conditions_canvas_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        
        canvas.create_window((0, 0), window=self.conditions_canvas_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        
        right_frame = ttk.Frame(main_frame)
        main_frame.add(right_frame, weight=1)
        
        ttk.Label(right_frame, text="Активные следствия", 
                 font=('Arial', 12, 'bold')).pack(pady=5)
        
        self.consequences_text = scrolledtext.ScrolledText(
            right_frame, wrap='word', font=('Arial', 10))
        self.consequences_text.pack(fill='both', expand=True, padx=5, pady=5)
        
        stats_frame = ttk.Frame(self.root)
        stats_frame.pack(fill='x', padx=5, pady=5)
        
        self.stats_label = ttk.Label(stats_frame, text="", font=('Arial', 10))
        self.stats_label.pack(side='left', padx=10)
        
        ttk.Button(stats_frame, text="Обновить", 
                  command=self.update_display).pack(side='right', padx=5)
    
    def open_llm_settings(self):
        dialog = LLMSettingsDialog(self.root, self.llm_settings)
        self.root.wait_window(dialog)
        
        if dialog.result:
            self.llm_settings = dialog.result
            self.hybrid_parser = HybridParser(
                use_llm=self.llm_settings['use_llm'],
                model_path=self.llm_settings['model_path'] if self.llm_settings['use_llm'] else None
            )
            
            if self.llm_settings['use_llm'] and self.hybrid_parser.llm_extractor:
                if self.hybrid_parser.llm_extractor.available:
                    self.llm_status_label.config(
                        text=f"LLM: включен ({self.llm_settings['n_ctx']} ctx)", 
                        foreground='green'
                    )
                else:
                    self.llm_status_label.config(text="LLM: ошибка", foreground='red')
            else:
                self.llm_status_label.config(text="LLM: выключен", foreground='gray')
            
            messagebox.showinfo("Успех", "Настройки LLM сохранены")
    
    def load_sample(self):
        sample = """
1. Общие положения
1.1 Настоящий стандарт устанавливает требования к проектированию зданий.
1.2 Если высота здания превышает 10 метров, то необходимо предусмотреть лифты.
1.3 При наличии подвальных помещений следует обеспечить гидроизоляцию.

2. Конструктивные требования
2.1 Все несущие конструкции должны быть рассчитаны на нагрузки.
2.2 Если здание расположено в сейсмической зоне, то применяются специальные меры усиления.
2.3 В случае использования железобетонных конструкций, необходимо обеспечить защитный слой бетона.

3. Пожарная безопасность
3.1 Если площадь этажа более 1000 кв.м, то требуется не менее двух эвакуационных выходов.
3.2 При высоте здания более 28 метров необходимо устройство пожарного лифта.
"""
        self.parser.parse_text(sample)
        self.parser.add_manual_consequence(
            text="Здание должно быть оборудовано лифтами и иметь усиленные конструкции",
            required_conditions=["1.2.1", "2.2.1"],
            source_clauses=["1.2", "2.2"]
        )
        self.update_display()
    
    def open_document(self):
        filename = filedialog.askopenfilename(
            title="Открыть документ",
            filetypes=[("Текстовые файлы", "*.txt"), ("Все файлы", "*.*")]
        )
        if filename:
            try:
                with open(filename, 'r', encoding='utf-8') as f:
                    text = f.read()
                self.parser = DocumentParser(self.hybrid_parser)
                self.checker = ComplianceChecker(self.parser)
                self.parser.parse_text(text)
                self.update_display()
                messagebox.showinfo("Успех", 
                    f"Документ загружен\nПунктов: {len(self.parser.clauses)}\nУсловий: {len(self.parser.conditions)}")
            except Exception as e:
                messagebox.showerror("Ошибка", f"Не удалось загрузить файл:\n{e}")
    
    def save_project(self):
        filename = filedialog.asksaveasfilename(
            title="Сохранить проект", defaultextension=".json",
            filetypes=[("JSON файлы", "*.json"), ("Все файлы", "*.*")]
        )
        if filename:
            try:
                data = {
                    'parser': self.parser.to_dict(),
                    'active_conditions': list(self.checker.active_conditions),
                    'llm_settings': self.llm_settings
                }
                with open(filename, 'w', encoding='utf-8') as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
                messagebox.showinfo("Успех", "Проект сохранен")
            except Exception as e:
                messagebox.showerror("Ошибка", f"Ошибка сохранения:\n{e}")
    
    def load_project(self):
        filename = filedialog.askopenfilename(
            title="Загрузить проект",
            filetypes=[("JSON файлы", "*.json"), ("Все файлы", "*.*")]
        )
        if filename:
            try:
                with open(filename, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                self.parser = DocumentParser(self.hybrid_parser)
                self.parser.from_dict(data['parser'])
                self.checker = ComplianceChecker(self.parser)
                self.checker.active_conditions = set(data['active_conditions'])
                if 'llm_settings' in data:
                    self.llm_settings = data['llm_settings']
                self.update_display()
                messagebox.showinfo("Успех", "Проект загружен")
            except Exception as e:
                messagebox.showerror("Ошибка", f"Ошибка загрузки:\n{e}")
    
    def add_consequence(self):
        dialog = AddConsequenceDialog(self.root, self.parser)
        self.root.wait_window(dialog)
        if dialog.result:
            self.parser.add_manual_consequence(
                text=dialog.result['text'],
                required_conditions=dialog.result['conditions']
            )
            self.update_display()
            messagebox.showinfo("Успех", "Следствие добавлено")
    
    def activate_all(self):
        for cid in self.parser.conditions:
            self.checker.activate_condition(cid)
        self.update_display()
    
    def deactivate_all(self):
        self.checker.active_conditions.clear()
        self.update_display()
    
    def on_search(self, *args):
        search_text = self.search_var.get().lower()
        for widget in self.conditions_canvas_frame.winfo_children():
            widget.destroy()
        
        self.condition_vars = {}
        for cond_id, condition in self.parser.conditions.items():
            if search_text in condition.text.lower() or search_text in cond_id.lower():
                var = tk.BooleanVar(value=cond_id in self.checker.active_conditions)
                var.trace('w', lambda *a, cid=cond_id, v=var: self.on_condition_toggle(cid, v))
                cb = tk.Checkbutton(
                    self.conditions_canvas_frame, 
                    text=f"{cond_id}: {condition.text}",
                    variable=var, anchor='w', wraplength=400, justify='left'
                )
                cb.pack(fill='x', padx=5, pady=2)
                self.condition_vars[cond_id] = var
    
    def on_condition_toggle(self, condition_id: str, var: tk.BooleanVar):
        if var.get():
            self.checker.activate_condition(condition_id)
        else:
            self.checker.deactivate_condition(condition_id)
        self.update_consequences()
        self.update_stats()
    
    def update_display(self):
        self.on_search()
        self.update_consequences()
        self.update_stats()
    
    def update_consequences(self):
        self.consequences_text.delete('1.0', tk.END)
        consequences = self.checker.get_active_consequences()
        
        if not consequences:
            self.consequences_text.insert('1.0', 
                "Нет активных следствий\n\nВыберите условия слева для просмотра следствий")
            return
        
        for cons in consequences:
            self.consequences_text.insert(tk.END, f"► {cons.text}\n", 'consequence')
            self.consequences_text.insert(tk.END, 
                f"  Требуемые условия: {', '.join(cons.required_conditions)}\n", 'details')
            if cons.source_clauses:
                self.consequences_text.insert(tk.END, 
                    f"  Источник: пункты {', '.join(cons.source_clauses)}\n", 'details')
            self.consequences_text.insert(tk.END, "\n")
        
        self.consequences_text.tag_config('consequence', 
            font=('Arial', 11, 'bold'), foreground='blue')
        self.consequences_text.tag_config('details', 
            font=('Arial', 9), foreground='gray')
    
    def update_stats(self):
        stats = self.checker.check_compliance()
        self.stats_label.config(
            text=f"Условий: {stats['active_conditions']}/{stats['total_conditions']} | "
                 f"Следствий: {stats['active_consequences']} | "
                 f"Покрытие: {stats['coverage']:.1f}%"
        )
    
    def show_about(self):
        messagebox.showinfo("О программе",
            "Система разбора нормативных документов\n\n"
            "Версия: 2.0 (с LLM)\n"
            "Разбор ГОСТ, СП, законов на пункты и условия\n"
            "Поддержка LLM через GGUF")


def main():
    root = tk.Tk()
    app = DocumentParserApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()