#!/usr/bin/env python3
"""Read-only ARM64 Mach-O string xrefs and bounded disassembly for ABI review.

Research dependency: capstone. This tool never loads or changes the application.
"""
import argparse
import bisect
from pathlib import Path
import struct


def image(path):
    data = Path(path).read_bytes()
    magic, count = struct.unpack_from('>II', data)
    if magic == 0xcafebabe:
        for i in range(count):
            cpu, _, offset, size, _ = struct.unpack_from('>IIIII', data, 8 + i * 20)
            if cpu == 0x100000c:
                data = data[offset:offset + size]
                break
        else:
            raise ValueError('No arm64 slice')
    if struct.unpack_from('<I', data)[0] != 0xfeedfacf:
        raise ValueError('Expected 64-bit Mach-O')
    commands = struct.unpack_from('<I', data, 16)[0]
    offset = 32
    sections, starts = {}, []
    function_data = None
    base = 0
    for _ in range(commands):
        command, size = struct.unpack_from('<II', data, offset)
        if command == 0x19:
            name = data[offset + 8:offset + 24].rstrip(b'\0').decode()
            address = struct.unpack_from('<Q', data, offset + 24)[0]
            if name == '__TEXT':
                base = address
            for i in range(struct.unpack_from('<I', data, offset + 64)[0]):
                at = offset + 72 + i * 80
                section = data[at:at + 16].rstrip(b'\0').decode()
                address, length, file_offset = struct.unpack_from('<QQI', data, at + 32)
                content = data[file_offset:file_offset + length] if file_offset else b''
                sections[name + ':' + section] = (address, content)
                sections[section] = (address, content)
        if command == 0x26:
            file_offset, length = struct.unpack_from('<II', data, offset + 8)
            function_data = data[file_offset:file_offset + length]
        offset += size
    if function_data:
        value = shift = 0
        address = base
        for byte in function_data:
            value |= (byte & 127) << shift
            if byte & 128:
                shift += 7
            else:
                if not value:
                    break
                address += value
                starts.append(address)
                value = shift = 0
    return sections, starts


def xrefs(sections, starts, query=None, reference=None):
    matches = []
    for name, (strings_base, strings) in sections.items():
        if not name.startswith('__TEXT:') or name.endswith(':__text'):
            continue
        at = strings.find(query.encode()) if query is not None else -1
        while at >= 0:
            begin = strings.rfind(b'\0', 0, at) + 1
            end = strings.find(b'\0', at)
            matches.append((strings_base + begin, strings[begin:end].decode(errors='replace')))
            at = strings.find(query.encode(), end + 1)
    targets = {address: text for address, text in matches}
    if reference is not None:
        targets[reference] = 'requested address'
    print('strings:', [(hex(address), text) for address, text in matches])
    base, code = sections['__text']
    for offset in range(0, len(code) - 4, 4):
        op, = struct.unpack_from('<I', code, offset)
        if op & 0x9f000000 != 0x90000000:
            continue
        immediate = ((op >> 5 & 0x7ffff) << 2) | (op >> 29 & 3)
        if immediate & 0x100000:
            immediate -= 0x200000
        page = ((base + offset) & ~4095) + (immediate << 12)
        register = op & 31
        for advance in range(4, 24, 4):
            following, = struct.unpack_from('<I', code, offset + advance)
            if following & 0xff000000 == 0x91000000 and following >> 5 & 31 == register:
                address = page + ((following >> 10 & 4095) << (12 if following & 0x400000 else 0))
                if address in targets:
                    index = bisect.bisect_right(starts, base + offset) - 1
                    print('xref', hex(base + offset), 'function', hex(starts[index]), targets[address])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--app', default='/Applications/CapCut.app/Contents/Frameworks/libvideoeditor.dylib')
    parser.add_argument('--string')
    parser.add_argument('--address', type=lambda n: int(n, 0))
    parser.add_argument('--pointers', type=lambda n: int(n, 0))
    parser.add_argument('--references', type=lambda n: int(n, 0))
    parser.add_argument('--calls', type=lambda n: int(n, 0))
    parser.add_argument('--data', type=lambda n: int(n, 0))
    parser.add_argument('--bytes', type=lambda n: int(n, 0), default=512)
    args = parser.parse_args()
    sections, starts = image(args.app)
    if args.string:
        xrefs(sections, starts, args.string)
    if args.references is not None:
        xrefs(sections, starts, reference=args.references)
    if args.pointers is not None:
        needle = struct.pack('<Q', args.pointers)
        for name, (base, data) in sections.items():
            if ':' not in name:
                continue
            offset = data.find(needle)
            while offset >= 0:
                print('pointer', name, hex(base + offset))
                offset = data.find(needle, offset + 1)
    if args.data is not None:
        for name, (base, data) in sections.items():
            if ':' in name and base <= args.data < base + len(data):
                offset = args.data - base
                for advance in range(0, min(args.bytes, len(data) - offset), 8):
                    block = data[offset + advance:offset + advance + 8]
                    print(hex(args.data + advance), block.hex(), hex(int.from_bytes(block, 'little')),
                          ''.join(chr(b) if 32 <= b < 127 else '.' for b in block))
    if args.calls is not None:
        base, code = sections['__text']
        for offset in range(0, len(code), 4):
            op, = struct.unpack_from('<I', code, offset)
            if op & 0x7c000000 != 0x14000000:
                continue
            immediate = op & 0x3ffffff
            if immediate & 0x2000000:
                immediate -= 0x4000000
            if base + offset + immediate * 4 == args.calls:
                index = bisect.bisect_right(starts, base + offset) - 1
                print('call', hex(base + offset), 'function', hex(starts[index]))
    if args.address is not None:
        from capstone import Cs, CS_ARCH_ARM64, CS_MODE_ARM
        base, code = sections['__text']
        offset = args.address - base
        if not 0 <= offset < len(code) or not 4 <= args.bytes <= 65536:
            raise ValueError('Disassembly range outside text or too large')
        index = bisect.bisect_right(starts, args.address) - 1
        print('nearby functions:', [hex(n) for n in starts[max(0, index - 4):index + 5]])
        for instruction in Cs(CS_ARCH_ARM64, CS_MODE_ARM).disasm(code[offset:offset + args.bytes], args.address):
            print(f'{instruction.address:#x}: {instruction.mnemonic} {instruction.op_str}')


if __name__ == '__main__':
    main()
