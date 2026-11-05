import struct, os

dmp_path = os.path.expandvars(r'%LOCALAPPDATA%\CrashDumps\eldenring.exe.7596.dmp')
with open(dmp_path, 'rb') as f:
    hdr = f.read(32)
    sig, ver, stream_cnt, stream_dir_rva, cksum, ts, flags = struct.unpack('<4sIIIIQ', hdr[:28]) + (0,)
    print(f'Sig: {sig}, streams: {stream_cnt}, dir_rva: {hex(stream_dir_rva)}')
    
    f.seek(stream_dir_rva)
    streams = []
    for _ in range(stream_cnt):
        st_type, data_sz, rva = struct.unpack('<III', f.read(12))
        streams.append((st_type, data_sz, rva))
    
    # 4 = ModuleListStream
    modules = []
    for st_type, data_sz, rva in streams:
        if st_type == 4:
            f.seek(rva)
            num_mods = struct.unpack('<I', f.read(4))[0]
            for _ in range(num_mods):
                entry_data = f.read(108)
                base, size, ck, ts, name_rva = struct.unpack('<QQIII', entry_data[:28])
                pos = f.tell()
                f.seek(name_rva)
                str_len = struct.unpack('<I', f.read(4))[0]
                name = f.read(str_len).decode('utf-16le', errors='ignore')
                modules.append((base, size, name))
                f.seek(pos)

    def find_mod(addr):
        for b, s, n in modules:
            if b <= addr < b + s:
                return f'{os.path.basename(n)} + 0x{addr - b:x}'
        return f'0x{addr:x}'

    for st_type, data_sz, rva in streams:
        if st_type == 6: # ExceptionStream
            f.seek(rva)
            # struct MINIDUMP_EXCEPTION_STREAM (x64: ThreadId=4, __alignment=4, ExceptionRecord=152 bytes, ContextRecord=16 bytes)
            tid, _pad = struct.unpack('<II', f.read(8))
            exc_code, exc_flags, exc_record, exc_addr, num_params = struct.unpack('<IIQQI', f.read(32))
            f.read(4 + 15 * 8) # params
            ctx_sz, ctx_rva = struct.unpack('<II', f.read(8))
            print(f'Exception: ThreadId={tid}, Code={hex(exc_code)}, Addr={find_mod(exc_addr)}')
            print(f'Context: sz={ctx_sz}, rva={hex(ctx_rva)}')
            
            f.seek(ctx_rva)
            ctx = f.read(ctx_sz)
            rip = struct.unpack_from('<Q', ctx, 248)[0]
            rsp = struct.unpack_from('<Q', ctx, 152)[0]
            rcx = struct.unpack_from('<Q', ctx, 128)[0]
            print(f'RIP={find_mod(rip)}, RSP={hex(rsp)}, RCX={hex(rcx)}')

            # Read stack memory
            for m_type, m_sz, m_rva in streams:
                if m_type == 9: # MemoryListStream
                    f.seek(m_rva)
                    num_mem = struct.unpack('<I', f.read(4))[0]
                    for _ in range(num_mem):
                        m_base, m_len, data_rva = struct.unpack('<QQI', f.read(16) + f.read(4))
                        f.read(4) # pad
                        if m_base <= rsp < m_base + m_len:
                            f.seek(data_rva + (rsp - m_base))
                            stack_raw = f.read(min(512, m_len - (rsp - m_base)))
                            print('Stack call candidates:')
                            for k in range(0, len(stack_raw)-8, 8):
                                w = struct.unpack_from('<Q', stack_raw, k)[0]
                                mod_str = find_mod(w)
                                if '+' in mod_str:
                                    print('  ', mod_str)
                            break
