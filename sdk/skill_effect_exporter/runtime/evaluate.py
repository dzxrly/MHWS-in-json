"""Run a skill-consuming function once per level and argument case."""

from __future__ import annotations

import itertools

from ..config import (
    ARGUMENT_REGISTERS,
    FIRST_STACK_ARGUMENT,
    HUNTER_SKILL,
    MAX_ARGUMENT_COMBINATIONS,
    MAX_ENUM_VALUES,
    OUT_PARAMETER_AREA,
    OUT_PARAMETER_STRIDE,
)
from ..native.emulator import STACK, Emulator, Stack, unknown_lanes
from ..native.values import Ptr, V, unk

FLOAT_TYPES = ("System.Single", "System.Double")


def argument_domains(layouts, params):
    """Small domains for Boolean and enum parameters; others stay unknown."""
    domains = []
    for index, param in enumerate(params):
        ptype = param.get("type")
        if param.get("modifier") == "ByRef":
            domains.append(None)  # passed as a pointer
        elif ptype == "System.Boolean":
            domains.append([("false", 0), ("true", 1)])
        elif layouts.is_enum(ptype):
            values = layouts.enum_values(ptype)
            if 0 < len(values) <= MAX_ENUM_VALUES:
                domains.append(
                    [(name, value & 0xFFFFFFFF) for name, value in values.items()]
                )
            else:
                domains.append(None)
        else:
            domains.append(None)
    combos, product = [], 1
    enumerated = []
    for index, domain in enumerate(domains):
        if domain is not None and product * len(domain) <= MAX_ARGUMENT_COMBINATIONS:
            product *= len(domain)
            enumerated.append(index)
    choices = [
        domains[i] if i in enumerated else [(None, None)] for i in range(len(domains))
    ]
    for combo in itertools.product(*choices):
        combos.append(combo)
    return combos


class Evaluator:
    def __init__(self, world: SkillWorld):
        self.world = world
        index = world.index
        self.names = dict(index.names)
        self.negations = {}  # shared by every run: condition text -> its negation
        self.signatures = {}  # callee address -> il2cpp method record, on demand
        self.skill_calls = frozenset()  # set by extract: skill-argument methods

    def signature(self, address):
        """il2cpp method record of a callee (returns, params, flags), or None."""
        if address not in self.signatures:
            record = None
            for type_name, method in self.world.index.catalog.get(address, []):
                methods = (self.world.metadata.get(type_name) or {}).get("methods", {})
                if method in methods:
                    record = methods[method]
                    break
            self.signatures[address] = record
        return self.signatures[address]

    def emulator(self, scenario):
        index = self.world.index

        def inline_ok(address):
            name = self.names.get(address)
            if name is None:
                return True  # unnamed helper bodies (inlined C# getters, BCL helpers)
            return not name.startswith(("System.Threading", "via.", "ace.cGameObject"))

        return Emulator(
            self.world.pe,
            scenario.heap,
            self.names,
            skip_calls={self.world.cookie},
            inline_ok=inline_ok,
            globals_=scenario.globals,
        )

    def run(self, scenario, function, info, args, sites=None):
        """Evaluate function once; with sites, only paths through one of them."""
        emulator = self.emulator(scenario)
        emulator.negations = self.negations
        emulator.signature = self.signature
        emulator.skill_calls = self.skill_calls
        if sites:
            start = int(function["address"], 16)
            emulator.focus = (
                start,
                self.world.pe.end(start),
                self.world.index.reaching(start, sites),
                frozenset(sites),
            )
        params = info.get("params", [])
        static = "Static" in info.get("flags", "")
        returns = info.get("returns", {}).get("type", "System.Void")
        declaring = function["type"]

        def setup(st):
            st.stack = Stack()
            st.regs["rsp"] = V(Ptr(STACK, 0))
            st.stack.write(0, 8, V("exit"))
            st.regs["rcx"] = V(Ptr(scenario.heap.unknown("app.ThreadContext", "线程")))
            arguments = []
            if not static:
                this = (
                    scenario.this
                    if declaring == HUNTER_SKILL
                    else scenario.heap.unknown(declaring, declaring.rsplit(".", 1)[-1])
                )
                arguments.append(("this", V(Ptr(this)), "object"))
            for position, (param, (label, value)) in enumerate(
                zip(params, args), start=1
            ):
                ptype = param.get("type")
                name = param.get("name") or f"参数{position}:{ptype.rsplit('.', 1)[-1]}"
                if value is not None:
                    arguments.append(
                        (name, V(value, frozenset({f"参数 {name}={label}"})), ptype)
                    )
                elif param.get("modifier") == "ByRef" or ptype.endswith("&"):
                    # ByRef: a pointer to a scratch slot holding an unknown initial value.
                    slot = OUT_PARAMETER_AREA - OUT_PARAMETER_STRIDE * len(arguments)
                    st.stack.write(slot, 8, unk(f"{name} 的传入值"))
                    arguments.append((name, V(Ptr(STACK, slot)), "pointer"))
                elif ptype in FLOAT_TYPES:
                    arguments.append((name, unk(name), ptype))
                elif scenario.world.layouts.is_value_type(ptype):
                    arguments.append((name, unk(name), ptype))
                else:
                    arguments.append(
                        (name, V(Ptr(scenario.heap.unknown(ptype, name))), ptype)
                    )
            registers = ARGUMENT_REGISTERS
            for position, (name, value, ptype) in enumerate(arguments):
                if position < len(registers):
                    if ptype in FLOAT_TYPES:
                        lanes = [value] + unknown_lanes(f"{name} 的高位")[1:]
                        st.vregs[position + 1] = lanes
                    else:
                        st.regs[registers[position]] = value
                else:
                    st.stack.write(
                        FIRST_STACK_ARGUMENT + 8 * (position - len(registers)), 8, value
                    )
            st.regs.setdefault("rbx", unk("调用者 rbx"))

        return emulator.run(int(function["address"], 16), setup, returns)
