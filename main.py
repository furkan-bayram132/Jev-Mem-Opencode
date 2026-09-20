#!/usr/bin/env python3
"""Jev-Mem build/query CLI. The existing MAGMA path remains the default."""

import argparse
from dataclasses import replace
from datetime import datetime
import hashlib
import json
import logging
from pathlib import Path
import subprocess
import sys

from dotenv import load_dotenv

from memory.memory_builder import MemoryBuilder
from memory.query_engine import QueryEngine
from memory.jev_mem_config import JevMemConfig


class JevMemSystem:
    def __init__(self, model="gpt-4o-mini", embedding_model="minilm", cache_dir="./cache",
                 sys1_config=None, memory_builder=None, *, jev_config=None):
        self.cache_dir = Path(cache_dir)
        if jev_config is not None and sys1_config is not None:
            raise ValueError("Pass only jev_config or the legacy sys1_config argument")
        config = jev_config or sys1_config or JevMemConfig()
        self.memory_builder = memory_builder if memory_builder is not None else MemoryBuilder(
            cache_dir=str(self.cache_dir), llm_model=model, embedding_model=embedding_model, sys1_config=config)
        self.trg_memory = self.memory_builder.trg
        self.graph_db = self.trg_memory.graph_db
        self.vector_db = self.trg_memory.vector_db
        self.llm_controller = self.memory_builder.llm_controller
        self.answer_formatter = self.memory_builder.answer_formatter
        self.query_engine = QueryEngine(self.trg_memory, self.memory_builder.node_index,
                                       sys1_config=self.memory_builder.sys1_config, jev_client=self.memory_builder.jev)

    def build_memory_from_conversation(self, conversation_data):
        """Accept raw observations; LoCoMo samples use the existing sample builder."""
        if hasattr(conversation_data, 'conversation'):
            return self.memory_builder.build_memory(conversation_data)
        if not isinstance(conversation_data, list):
            raise ValueError("Input must be a JSON list of strings or objects with content/text")
        # Validate the full input before any insertion.
        observations = []
        for item in conversation_data:
            if isinstance(item, str):
                item = {"content": item}
            if not isinstance(item, dict):
                raise ValueError("Each observation must be a string or object")
            content = item.get('content', item.get('text'))
            if not isinstance(content, str) or not content.strip():
                raise ValueError("Each observation needs non-empty content or text")
            timestamp = item.get('timestamp')
            if isinstance(timestamp, str):
                timestamp = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
            if timestamp is not None and not isinstance(timestamp, datetime):
                raise ValueError("timestamp must be ISO 8601 text or null")
            metadata = item.get('metadata', {})
            if not isinstance(metadata, dict):
                raise ValueError("metadata must be an object")
            observations.append((content, timestamp, metadata))
        admitted = sum(self.memory_builder.build(content, timestamp, metadata) is not None
                       for content, timestamp, metadata in observations)
        return {"admitted": admitted, "rejected": len(observations) - admitted}

    def query(self, question):
        context, evidence = self.query_engine.query(question, top_k=5)
        if not self.llm_controller:
            return evidence or "Information not found"
        prompt = self.answer_formatter.build_qa_prompt(evidence, question)
        response = self.llm_controller.llm.get_completion(prompt, response_format={"type": "text"}, temperature=0.0)
        self.memory_builder.jev.audit.emit("system_two_answer", query_id=context.metadata.get('query_id'), llm_calls=1)
        return self.answer_formatter.extract_answer(response, question)

    def save_memory(self, save_path=None):
        if save_path is not None:
            self.memory_builder.cache_dir = Path(save_path)
        self.memory_builder.save()

    def load_memory(self, load_path=None):
        if load_path is not None:
            self.memory_builder.cache_dir = Path(load_path)
        self.memory_builder.load()
        self.query_engine.node_index = self.memory_builder.node_index


# Preserve the legacy public class name.
TRGSystem = JevMemSystem
Sys1MemSystem = JevMemSystem


def main():
    parser = argparse.ArgumentParser(description='Jev-Mem memory construction and retrieval')
    parser.add_argument('--mode', choices=['build', 'query', 'test'], default='test')
    parser.add_argument('--input', help='Observation JSON for build; LoCoMo JSON for test')
    parser.add_argument('--question')
    parser.add_argument('--model', default='gpt-4o-mini')
    parser.add_argument('--embedding-model', default='minilm', choices=['minilm', 'openai'])
    parser.add_argument('--cache-dir', default='./cache')
    parser.add_argument('--jev-mem', '--sys1mem', dest='sys1mem', action='store_true')
    parser.add_argument('--jev-config', '--sys1-config', dest='sys1_config')
    parser.add_argument('--jev-mock', action='store_true')
    parser.add_argument('--no-jev-write', '--no-sys1-write', dest='no_sys1_write', action='store_true')
    parser.add_argument('--no-jev-read', '--no-sys1-read', dest='no_sys1_read', action='store_true')
    args = parser.parse_args()
    if args.mode in ('build', 'test') and not args.input:
        parser.error('--input is required for build/test')
    if args.mode == 'query' and not args.question:
        parser.error('--question is required for query')
    load_dotenv()
    logging.basicConfig(level=logging.INFO)
    if args.mode == 'test':
        command = [sys.executable, str(Path(__file__).with_name('test_fixed_memory.py')),
                   '--dataset', args.input, '--model', args.model, '--embedding-model', args.embedding_model,
                   '--cache-dir', args.cache_dir]
        for flag in ('sys1mem', 'jev_mock', 'no_sys1_write', 'no_sys1_read'):
            if getattr(args, flag):
                command.append('--' + flag.replace('_', '-'))
        if args.sys1_config:
            command.extend(['--sys1-config', args.sys1_config])
        return subprocess.call(command)
    overrides = {}
    if args.sys1mem:
        overrides.update(write_enabled=True, read_enabled=True)
    if args.jev_mock:
        overrides['jev_mock'] = True
    if args.no_sys1_write:
        overrides['write_enabled'] = False
    if args.no_sys1_read:
        overrides['read_enabled'] = False
    config = JevMemConfig.load(args.sys1_config, **overrides)
    cache_dir = Path(args.cache_dir)
    if config.write_enabled or config.read_enabled:
        digest = hashlib.sha256(json.dumps(config.to_dict(), sort_keys=True).encode()).hexdigest()[:12]
        cache_dir /= 'jev_mem_' + digest
        config = replace(config, audit_path=config.audit_path or str(cache_dir / 'decisions.jsonl'))
    system = JevMemSystem(args.model, args.embedding_model, str(cache_dir), config)
    if args.mode == 'build':
        if (cache_dir / 'graph.json').exists():
            system.load_memory()
        data = json.loads(Path(args.input).read_text())
        print(json.dumps(system.build_memory_from_conversation(data)))
        system.save_memory()
    else:
        if not (cache_dir / 'graph.json').exists():
            parser.error('No saved graph in ' + str(cache_dir))
        system.load_memory()
        print(system.query(args.question))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
