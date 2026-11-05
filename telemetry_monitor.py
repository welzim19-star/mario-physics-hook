#!/usr/bin/env python3
"""
Mario 64 Physics - Live Telemetry Monitor & Wallhack Inspector
============================================================
Connects directly to Elden Ring / mario64_physics.dll via Windows Named Shared Memory
and/or streams events from mario_telemetry.log in real time.

Usage:
    python telemetry_monitor.py --live         (Interactive live ASCII HUD dashboard)
    python telemetry_monitor.py --tail         (Stream collision and physics events in real time)
    python telemetry_monitor.py --snapshot     (Print instant state snapshot and exit)
    python telemetry_monitor.py --summary      (Analyze recent telemetry log history)
"""

import sys
import os
import time
import mmap
import ctypes
import argparse

# -----------------------------------------------------------------------------
# C-Compatible Struct matching MarioTelemetryData in dll_main.cpp
# -----------------------------------------------------------------------------
class MarioTelemetryData(ctypes.Structure):
    _pack_ = 1
    _fields_ = [
        ("magic", ctypes.c_uint32),            # 0x4D41524F ("MARO")
        ("version", ctypes.c_uint32),          # 1
        ("tick_count", ctypes.c_uint64),
        ("time_ms", ctypes.c_uint64),

        # ER World Position & Orientation
        ("er_x", ctypes.c_float),
        ("er_y", ctypes.c_float),
        ("er_z", ctypes.c_float),
        ("face_angle", ctypes.c_float),

        # SM64 Local Position & Origin
        ("origin_x", ctypes.c_float),
        ("origin_y", ctypes.c_float),
        ("origin_z", ctypes.c_float),
        ("sm64_x", ctypes.c_float),
        ("sm64_y", ctypes.c_float),
        ("sm64_z", ctypes.c_float),

        # Speeds & Velocities
        ("vel_x", ctypes.c_float),
        ("vel_y", ctypes.c_float),
        ("vel_z", ctypes.c_float),
        ("horiz_speed", ctypes.c_float),
        ("vert_speed", ctypes.c_float),

        # Action State
        ("action", ctypes.c_uint32),
        ("prev_action", ctypes.c_uint32),
        ("action_timer", ctypes.c_uint32),
        ("action_name", ctypes.c_char * 32),
        ("is_airborne", ctypes.c_uint8),
        ("is_grounded", ctypes.c_uint8),

        # Inputs
        ("stick_x", ctypes.c_float),
        ("stick_y", ctypes.c_float),
        ("btn_a", ctypes.c_uint8),
        ("btn_b", ctypes.c_uint8),
        ("btn_z", ctypes.c_uint8),
        ("pad_connected", ctypes.c_uint8),

        # Environment Collision Probes
        ("ground_found", ctypes.c_uint8),
        ("ground_y", ctypes.c_float),
        ("drop_dist", ctypes.c_float),
        ("ground_layer", ctypes.c_uint32),

        ("wall_hit", ctypes.c_uint8),
        ("wall_hit_dist", ctypes.c_float),
        ("wall_hit_x", ctypes.c_float),
        ("wall_hit_y", ctypes.c_float),
        ("wall_hit_z", ctypes.c_float),
        ("wall_layer", ctypes.c_uint32),

        ("ceiling_hit", ctypes.c_uint8),
        ("ceiling_y", ctypes.c_float),

        # Health / Combat
        ("health", ctypes.c_int16),
        ("enemies_hit_count", ctypes.c_uint32),
    ]

SHM_NAME = "Local\\Mario64Telemetry"
LOG_PATH = r"D:\Modding\MarioPhysics\mario_telemetry.log"

def layer_name(layer: int) -> str:
    if layer == 0x2000058:
        return "0x2000058 [Door / Gate / Lever / Prop]"
    elif layer == 0x1704:
        return "0x0001704 [Player Dynamic Collider]"
    elif layer == 0x08:
        return "0x0000008 [Static Terrain / Ground]"
    elif layer == 0xCA9501E:
        return "Havok Capsule Contact Fallback"
    elif layer == 0:
        return "None"
    else:
        return f"0x{layer:08X}"

def read_shared_memory() -> MarioTelemetryData:
    try:
        shm = mmap.mmap(-1, ctypes.sizeof(MarioTelemetryData), SHM_NAME, access=mmap.ACCESS_READ)
        data = MarioTelemetryData.from_buffer_copy(shm.read(ctypes.sizeof(MarioTelemetryData)))
        shm.close()
        if data.magic == 0x4D41524F:
            return data
    except Exception:
        pass
    return None

def print_snapshot(data: MarioTelemetryData):
    if not data:
        print("[AVISO] Shared memory 'Local\\Mario64Telemetry' nao encontrada ou Elden Ring ainda nao carregou o mod com telemetria.")
        print(f"Verifique se o jogo foi reiniciado e se {LOG_PATH} esta sendo gerado.")
        return

    act_str = data.action_name.decode("utf-8", errors="ignore")
    print("=" * 70)
    print("        MARIO 64 PHYSICS TELEMETRY - SNAPSHOT INSTANTANEO")
    print("=" * 70)
    print(f"  Ticks Totais:    {data.tick_count} (tempo mod: {data.time_ms / 1000.0:.2f}s)")
    print(f"  Acao SM64:       {act_str} (0x{data.action:08X}) [duracao: {data.action_timer} ticks]")
    print(f"  Estado Aereo:    {'AR / NO AR' if data.is_airborne else 'NO CHAO (GROUNDED)'}")
    print("-" * 70)
    print(f"  Posicao Elden:   X={data.er_x:9.3f} | Y={data.er_y:9.3f} (altura) | Z={data.er_z:9.3f}")
    print(f"  Posicao SM64:    X={data.sm64_x:9.2f} | Y={data.sm64_y:9.2f}          | Z={data.sm64_z:9.2f}")
    print(f"  Origem Mundo:    X={data.origin_x:9.3f} | Y={data.origin_y:9.3f}          | Z={data.origin_z:9.3f}")
    print(f"  Velocidade:      H_SPD={data.horiz_speed:6.2f} m/s | V_SPD={data.vert_speed:6.2f} (Y) | FaceAngle={data.face_angle:5.2f} rad")
    print("-" * 70)
    print(f"  Inputs:          Stick=({data.stick_x:+.2f}, {data.stick_y:+.2f}) | Pulo(A)={data.btn_a} | Soco(B)={data.btn_b} | Agachar(Z)={data.btn_z}")
    print(f"  Gamepad:         {'Conectado' if data.pad_connected else 'Teclado/Mouse'}")
    print("-" * 70)
    print("  COLISAO COM O AMBIENTE:")
    gnd_status = "DETECTADO" if data.ground_found else "NAO ENCONTRADO!"
    print(f"  - Chao (Ground): {gnd_status} | Altura Chao={data.ground_y:8.3f}m | DropDist={data.drop_dist:+.3f}m")
    print(f"                   Camada Havok: {layer_name(data.ground_layer)}")
    wall_status = f"COLISAO ATIVA! (dist={data.wall_hit_dist:.2f}m)" if data.wall_hit else "Livre (sem colisao)"
    print(f"  - Parede/Porta:  {wall_status}")
    if data.wall_hit:
        print(f"                   Ponto de Contato: ({data.wall_hit_x:.2f}, {data.wall_hit_y:.2f}, {data.wall_hit_z:.2f})")
        print(f"                   Camada Havok: {layer_name(data.wall_layer)}")
    ceil_status = f"BATIDA DE CABECA! (Y={data.ceiling_y:.2f}m)" if data.ceiling_hit else "Livre acima"
    print(f"  - Teto (Ceiling): {ceil_status}")
    print("-" * 70)
    print(f"  Vida (HP SM64):  0x{data.health:04X} (Imortal)")
    print(f"  Inimigos Atingidos: {data.enemies_hit_count}")
    print("=" * 70)

def run_live():
    print("[TELEMETRY] Aguardando conexao com Elden Ring (Local\\Mario64Telemetry)...")
    last_tick = -1
    spinner = ["|", "/", "-", "\\"]
    sp_idx = 0

    while True:
        data = read_shared_memory()
        if not data:
            sys.stdout.write(f"\r[STATUS] Aguardando jogo iniciar / carregar mod... {spinner[sp_idx % 4]}")
            sys.stdout.flush()
            sp_idx += 1
            time.sleep(0.5)
            continue

        if data.tick_count != last_tick:
            last_tick = data.tick_count
            # Clear screen
            os.system("cls" if os.name == "nt" else "clear")
            print_snapshot(data)
            print("  [Pressione Ctrl+C para sair do painel live]")
        time.sleep(0.05)

def run_tail():
    if not os.path.exists(LOG_PATH):
        print(f"[AVISO] Arquivo {LOG_PATH} ainda nao existe.")
        print("Aguardando geracao pelo jogo...")
        while not os.path.exists(LOG_PATH):
            time.sleep(1)

    print(f"=== SEGUINDO EVENTOS DE TELEMETRIA EM TEMPO REAL ({LOG_PATH}) ===")
    with open(LOG_PATH, "r", encoding="utf-8", errors="ignore") as f:
        # Move to end
        f.seek(0, os.SEEK_END)
        while True:
            line = f.readline()
            if line:
                line_str = line.strip()
                # Simple color-coding by tag
                if "[WALL_HIT  ]" in line_str:
                    print(f"\033[91m{line_str}\033[0m") # Red
                elif "[CEILING_HI]" in line_str or "[CEILING_HIT]" in line_str:
                    print(f"\033[93m{line_str}\033[0m") # Yellow
                elif "[LEDGE_DROP]" in line_str:
                    print(f"\033[95m{line_str}\033[0m") # Magenta
                elif "[STEP      ]" in line_str:
                    print(f"\033[96m{line_str}\033[0m") # Cyan
                elif "[ACTION    ]" in line_str:
                    print(f"\033[92m{line_str}\033[0m") # Green
                elif "[COMBAT    ]" in line_str:
                    print(f"\033[97;41m{line_str}\033[0m") # White on Red
                else:
                    print(line_str)
            else:
                time.sleep(0.05)

def run_summary():
    if not os.path.exists(LOG_PATH):
        print(f"[ERRO] {LOG_PATH} nao encontrado.")
        return

    with open(LOG_PATH, "r", encoding="utf-8", errors="ignore") as f:
        lines = f.readlines()

    wall_hits = 0
    ceil_hits = 0
    ledge_drops = 0
    steps = 0
    actions = {}
    combats = 0

    for line in lines:
        if "[WALL_HIT" in line:
            wall_hits += 1
        elif "[CEILING_HI" in line:
            ceil_hits += 1
        elif "[LEDGE_DROP" in line:
            ledge_drops += 1
        elif "[STEP" in line:
            steps += 1
        elif "[COMBAT" in line:
            combats += 1
        elif "[ACTION" in line:
            parts = line.split("->")
            if len(parts) > 1:
                act = parts[1].split()[0]
                actions[act] = actions.get(act, 0) + 1

    print("=" * 60)
    print("      RELATORIO DE TELEMETRIA E COLISAO - MARIO 64 ER")
    print("=" * 60)
    print(f"  Total de Linhas no Log:     {len(lines)}")
    print(f"  Colisoes com Parede/Portas: {wall_hits}")
    print(f"  Batidas de Cabeca no Teto:  {ceil_hits}")
    print(f"  Quedas de Beirada/Telhado:  {ledge_drops}")
    print(f"  Ajustes de Degrau/Escada:   {steps}")
    print(f"  Golpes de Combate em Mobs:  {combats}")
    print("-" * 60)
    print("  Distribuicao de Transicoes de Acao:")
    for act, cnt in sorted(actions.items(), key=lambda x: -x[1])[:10]:
        print(f"    - {act:<25}: {cnt} vezes")
    print("=" * 60)

def main():
    parser = argparse.ArgumentParser(description="Mario 64 Telemetry Monitor")
    parser.add_argument("--live", action="store_true", help="Live HUD dashboard")
    parser.add_argument("--tail", action="store_true", help="Stream log events in real time")
    parser.add_argument("--snapshot", action="store_true", help="Print single snapshot and exit")
    parser.add_argument("--summary", action="store_true", help="Analyze telemetry log statistics")
    args = parser.parse_args()

    if args.tail:
        run_tail()
    elif args.snapshot:
        data = read_shared_memory()
        print_snapshot(data)
    elif args.summary:
        run_summary()
    else:
        # Default to snapshot if not live, or live if interactive
        if args.live:
            run_live()
        else:
            data = read_shared_memory()
            if data:
                print_snapshot(data)
            else:
                parser.print_help()
                print("\n[DICA] Use 'python telemetry_monitor.py --live' para o painel em tempo real,")
                print("       ou 'python telemetry_monitor.py --tail' para acompanhar os eventos de colisao!")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n[TELEMETRY] Monitor finalizado.")

