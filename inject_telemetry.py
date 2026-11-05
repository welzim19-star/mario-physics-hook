import sys

with open(r'D:\Modding\MarioPhysics\src\dll_main.cpp', 'r', encoding='utf-8') as f:
    content = f.read()

# 1. Telemetry declarations & helper functions
telemetry_block = '''
// --- SM64 Action Name Decoder & Telemetry System ---
static const char* GetSM64ActionName(uint32_t act) {
    switch (act) {
        // Stationary
        case 0x0C400201: return "ACT_IDLE";
        case 0x0C400202: return "ACT_START_SLEEPING";
        case 0x0C400203: return "ACT_SLEEPING";
        case 0x0C400204: return "ACT_WAKING_UP";
        case 0x0C400205: return "ACT_PANTING";
        case 0x0C008220: return "ACT_CROUCHING";
        case 0x0C008221: return "ACT_START_CROUCHING";
        case 0x0C008222: return "ACT_STOP_CROUCHING";
        case 0x08000236: return "ACT_GROUND_POUND_LAND";
        case 0x08000238: return "ACT_TRIPLE_JUMP_LAND";
        case 0x08000239: return "ACT_CROUCH_SLIDE";
        case 0x0800023B: return "ACT_BRAKING";
        case 0x0800023C: return "ACT_DECELERATING";
        case 0x0080023A: return "ACT_HARD_BACKWARD_GROUND_KB";

        // Moving
        case 0x04000440: return "ACT_WALKING";
        case 0x04000442: return "ACT_HOLD_WALKING";
        case 0x04000443: return "ACT_START_CRAWLING";
        case 0x04000444: return "ACT_CRAWLING";
        case 0x04000445: return "ACT_STOP_CRAWLING";
        case 0x00000446: return "ACT_TURNING_AROUND";
        case 0x00000447: return "ACT_FINISH_TURNING_AROUND";
        case 0x00800457: return "ACT_MOVE_PUNCHING";
        case 0x01800458: return "ACT_SLIDE_KICK";
        case 0x00800459: return "ACT_SLIDE_KICK_SLIDE";
        case 0x00880456: return "ACT_DIVE_SLIDE";
        case 0x00020464: return "ACT_BUTT_SLIDE";
        case 0x00000468: return "ACT_STOMACH_SLIDE";
        case 0x00000386: return "ACT_STOMACH_SLIDE_STOP";
        case 0x04000474: return "ACT_FORWARD_GROUND_ODD";
        case 0x00000477: return "ACT_BACKWARD_GROUND_ODD";

        // Airborne
        case 0x03000880: return "ACT_JUMP";
        case 0x03000881: return "ACT_DOUBLE_JUMP";
        case 0x01000882: return "ACT_TRIPLE_JUMP";
        case 0x01000883: return "ACT_BACKFLIP";
        case 0x01000884: return "ACT_STEEP_JUMP";
        case 0x03000885: return "ACT_SIDE_FLIP";
        case 0x03000886: return "ACT_WALL_KICK_AIR";
        case 0x03000888: return "ACT_LONG_JUMP";
        case 0x0188088A: return "ACT_WATER_JUMP";
        case 0x0100088C: return "ACT_FREEFALL";
        case 0x00880898: return "ACT_DIVE";
        case 0x008008A3: return "ACT_JUMP_KICK";
        case 0x008008A4: return "ACT_GROUND_POUND";
        case 0x010008A6: return "ACT_FORWARD_ROLLOUT";
        case 0x010008A7: return "ACT_BACKWARD_ROLLOUT";
        case 0x00000473: return "ACT_AIR_HIT_WALL";
        case 0x000208B0: return "ACT_SOFT_BONK";
        case 0x000208B6: return "ACT_HARD_AIR_KB";

        // Object / Action
        case 0x00800380: return "ACT_PUNCHING";
        case 0x00800382: return "ACT_PICKING_UP";
        case 0x000008FF: return "ACT_HOLDING_BOWSER";

        default: {
            uint32_t grp = act & 0x000001C0;
            if (grp == 0x00000000) return "ACT_STATIONARY";
            if (grp == 0x00000040) return "ACT_MOVING";
            if (grp == 0x00000080) return "ACT_AIRBORNE";
            if (grp == 0x000000C0) return "ACT_SUBMERGED";
            if (grp == 0x00000100) return "ACT_CUTSCENE";
            return "ACT_UNKNOWN";
        }
    }
}

#pragma pack(push, 1)
struct MarioTelemetryData {
    uint32_t magic;             // "MARO" = 0x4D41524F
    uint32_t version;           // 1
    uint64_t tickCount;         // total 30Hz ticks
    uint64_t timeMs;            // timestamp in ms

    // ER World Position & Orientation
    float erX, erY, erZ;
    float faceAngle;            // radians

    // SM64 Local Position & Origin
    float originX, originY, originZ;
    float sm64X, sm64Y, sm64Z;

    // Speeds & Velocities
    float velX, velY, velZ;
    float horizSpeed;
    float vertSpeed;

    // Action State
    uint32_t action;
    uint32_t prevAction;
    uint32_t actionTimer;
    char actionName[32];
    uint8_t isAirborne;
    uint8_t isGrounded;

    // Inputs
    float stickX, stickY;
    uint8_t btnA, btnB, btnZ;
    uint8_t padConnected;

    // Environment Collision Probes
    uint8_t groundFound;
    float groundY;
    float dropDist;             // currentErPos.y - groundHit.y
    uint32_t groundLayer;

    uint8_t wallHit;
    float wallHitDist;
    float wallHitX, wallHitY, wallHitZ;
    uint32_t wallLayer;

    uint8_t ceilingHit;
    float ceilingY;

    // Health / Combat
    int16_t health;
    uint32_t enemiesHitCount;
};
#pragma pack(pop)

static HANDLE g_hTelemetryMap = NULL;
static MarioTelemetryData* g_pTelemetryShm = nullptr;
static std::mutex g_TelemetryMutex;
static FILE* g_TelemetryLogFile = nullptr;
static uint64_t g_TelemetryTickCount = 0;
static std::atomic<uint32_t> g_EnemiesHitCount{0};

static void InitTelemetry() {
    if (!g_hTelemetryMap) {
        g_hTelemetryMap = CreateFileMappingA(
            INVALID_HANDLE_VALUE,
            nullptr,
            PAGE_READWRITE,
            0,
            sizeof(MarioTelemetryData),
            "Local\\\\Mario64Telemetry"
        );
        if (g_hTelemetryMap) {
            g_pTelemetryShm = (MarioTelemetryData*)MapViewOfFile(
                g_hTelemetryMap,
                FILE_MAP_ALL_ACCESS,
                0, 0,
                sizeof(MarioTelemetryData)
            );
            if (g_pTelemetryShm) {
                memset(g_pTelemetryShm, 0, sizeof(MarioTelemetryData));
                g_pTelemetryShm->magic = 0x4D41524F;
                g_pTelemetryShm->version = 1;
            }
        }
    }
    if (!g_TelemetryLogFile) {
        g_TelemetryLogFile = fopen("D:\\\\Modding\\\\MarioPhysics\\\\mario_telemetry.log", "w");
        if (g_TelemetryLogFile) {
            fprintf(g_TelemetryLogFile, "=== MARIO 64 PHYSICS TELEMETRY LOG INITIALIZED ===\\n");
            fprintf(g_TelemetryLogFile, "[TIME_MS] [TAG       ] Details...\\n");
            fflush(g_TelemetryLogFile);
        }
    }
}

static void LogTelemetryEvent(const char* tag, const char* fmt, ...) {
    std::lock_guard<std::mutex> lock(g_TelemetryMutex);
    if (!g_TelemetryLogFile) return;

    DWORD t = timeGetTime();
    uint32_t ms = t % 1000;
    uint32_t s = (t / 1000) % 60;
    uint32_t m = (t / 60000) % 60;
    uint32_t h = (t / 3600000);

    fprintf(g_TelemetryLogFile, "[%02u:%02u:%02u.%03u] [%-10s] ", h, m, s, ms, tag);

    va_list args;
    va_start(args, fmt);
    vfprintf(g_TelemetryLogFile, fmt, args);
    va_end(args);

    fprintf(g_TelemetryLogFile, "\\n");
    fflush(g_TelemetryLogFile);
}
'''

target1 = '// --- Globals ---'
if target1 in content:
    content = content.replace(target1, telemetry_block + '\n' + target1, 1)
    print("Step 1 injected: Telemetry declarations")
else:
    print("Error: Target 1 not found!")
    sys.exit(1)

# 2. Update CastWallRay to record layer
old_cast_wall_ray = '''static bool CastWallRay(uintptr_t exeBase, uintptr_t playerIns, const Vec3& from, const Vec3& delta, Vec3& hitPoint) {
    if (CastRayER(exeBase, playerIns, from, delta, hitPoint, 0x2000058)) return true;
    if (CastRayER(exeBase, playerIns, from, delta, hitPoint, 0x1704)) return true;
    return CastRayER(exeBase, playerIns, from, delta, hitPoint, 0x08);
}'''

new_cast_wall_ray = '''static bool CastWallRay(uintptr_t exeBase, uintptr_t playerIns, const Vec3& from, const Vec3& delta, Vec3& hitPoint, uint32_t* outFilter = nullptr) {
    if (CastRayER(exeBase, playerIns, from, delta, hitPoint, 0x2000058)) {
        if (outFilter) *outFilter = 0x2000058;
        return true;
    }
    if (CastRayER(exeBase, playerIns, from, delta, hitPoint, 0x1704)) {
        if (outFilter) *outFilter = 0x1704;
        return true;
    }
    if (CastRayER(exeBase, playerIns, from, delta, hitPoint, 0x08)) {
        if (outFilter) *outFilter = 0x08;
        return true;
    }
    return false;
}'''

if old_cast_wall_ray in content:
    content = content.replace(old_cast_wall_ray, new_cast_wall_ray, 1)
    print("Step 2 injected: CastWallRay with outFilter")
else:
    print("Warning: old_cast_wall_ray exact text not found, checking normalized whitespace...")
    # fallback with regex or CRLF
    normalized_old = old_cast_wall_ray.replace('\n', '\r\n')
    if normalized_old in content:
        content = content.replace(normalized_old, new_cast_wall_ray.replace('\n', '\r\n'), 1)
        print("Step 2 injected: CastWallRay (CRLF matched)")
    else:
        print("Error: CastWallRay not found!")
        sys.exit(1)

# 3. Call InitTelemetry in MainLoopThread
old_thread_start = 'timeBeginPeriod(1);'
new_thread_start = 'timeBeginPeriod(1);\n    InitTelemetry();'
if old_thread_start in content:
    content = content.replace(old_thread_start, new_thread_start, 1)
    print("Step 3 injected: InitTelemetry call")

# 4. In DealMarioCombatDamage: increment g_EnemiesHitCount and log
old_combat_hit = 'LogMsg("[COMBAT] Mario ACERTOU inimigo/boss %p'
if old_combat_hit in content:
    combat_repl = 'g_EnemiesHitCount++;\n                LogTelemetryEvent("COMBAT", "Mario HIT enemy %p (HP %d->%d, -%d)", (void*)chr, hp, newHp, dmg);\n                ' + old_combat_hit
    content = content.replace(old_combat_hit, combat_repl, 1)
    print("Step 4 injected: Combat telemetry")

with open(r'D:\Modding\MarioPhysics\src\dll_main.cpp', 'w', encoding='utf-8') as f:
    f.write(content)

print("Steps 1-4 successfully saved.")

