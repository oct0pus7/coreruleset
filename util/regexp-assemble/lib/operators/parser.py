import re, os
from typing import Mapping
import logging

from msc_pyparser import MSCParser
from lib.context import Context
from lib.operators.assembler import Assembler


class Parser(object):
    rule_id_regex = re.compile(r"^(\d{6})(?:-chain(\d+))?")
    parsers: Mapping[str, MSCParser] = {}
    prefix_to_file_map: Mapping[str, str] = {}
    logger = logging.getLogger()

    def __init__(self, context: Context):
        self.context = context

    def perform_compare_or_update(self, process_all: bool, func=None):
        files = os.listdir(self.context.data_files_directory)
        files.sort()
        for file in files:
            if process_all:
                match = self.rule_id_regex.match(os.path.basename(file))
                rule_id = match.group(1)
                chain_offset = int(match.group(2)) if match.group(2) else 0
            else:
                rule_id = self.context.single_rule_id
                chain_offset = self.context.single_chain_offset

            if rule_id in file and ('chain' not in file or f'chain{chain_offset}' in file):
                self.process_regex(
                    rule_id,
                    chain_offset,
                    os.path.join(self.context.data_files_directory, file),
                    Assembler(self.context),
                    func,
                )
                if not process_all:
                    break

    def process_regex(self, rule_id: str, chain_offset: int, file_path: str, assembler: Assembler, func):
        self.logger.info("Processing %s, chain offset %s", rule_id, chain_offset)

        with open(file_path, "rt") as file:
            regex = assembler.run(file)

        rule_prefix = rule_id[:3]
        if rule_prefix in self.parsers:
            parser = self.parsers[rule_prefix]
        else:
            for rule_file in os.listdir(self.context.rules_directory):
                if rule_prefix in rule_file:
                    self.prefix_to_file_map[rule_prefix] = rule_file
                    with open(
                        os.path.join(self.context.rules_directory, rule_file), "rt"
                    ) as handle:
                        parser = MSCParser()
                        self.parsers[rule_prefix] = parser
                        parser.parser.parse(handle.read())
                        break
            if not parser:
                raise Warning(f"No rule file found for data file {file}")

        self.process_configlines(parser.configlines, file_path, rule_id, chain_offset, regex, func)

    def process_configlines(self, configlines, file_path, rule_id, chain_offset, regex, func):
        current_chain_offset = 0
        check_chain_rules = False

        for config in configlines:
            if config["type"] == "SecRule":
                if check_chain_rules and "id" not in config["actions"]:
                    current_chain_offset += 1
                    if current_chain_offset == chain_offset:
                        if config["operator"] != "@rx":
                            raise Warning(f"Rule {rule_id} does not use the @rx operator, but {config['operator']}")

                        func(
                            rule_id,
                            regex,
                            config["operator_argument"],
                            config,
                            "operator_argument",
                        )
                        return
                else:
                    if check_chain_rules:
                        raise Warning(f"Chain rule with ID {rule_id} and offset {chain_offset} not found in file {file_path}")

                    for action in config["actions"]:
                        if action["act_name"] == "id" and action["act_arg"] == rule_id:
                            if chain_offset == 0:
                                if config["operator"] != "@rx":
                                    raise Warning(f"Rule {rule_id} does not use the @rx operator, but {config['operator']}")

                                func(
                                    rule_id,
                                    regex,
                                    config["operator_argument"],
                                    config,
                                    "operator_argument",
                                )
                                return
                            else:
                                check_chain_rules = True
                                break
