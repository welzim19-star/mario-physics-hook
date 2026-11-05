#include <windows.h>

#include <mmsystem.h>

#include <xinput.h>

#include <psapi.h>

#include <tlhelp32.h>

#include <cmath>

#include <cstdint>

#include <cstdio>

#include <cstring>

#include <vector>

#include <mutex>

#include <atomic>

#include <algorithm>

#include "../minhook/include/MinHook.h"

extern "C" {

#include "D:/Modding/er-mario/libsm64/src/libsm64.h"

}

static constexpr float PI_F = 3.14159265358979323846f;

static constexpr float SCALE_ER = 0.01f;       // 1 SM64 unit = 0.01 m

static constexpr float MODEL_SCALE = 0.25f;    // SM64 geo layout scale

static constexpr int SM64_PARTS = 16;

static constexpr int TOTAL_PARTS = 21;

static constexpr int HEAD_PART = 3;

static constexpr int RIGHT_HAND_PART = 9;

static constexpr int PEACE_PART = 20;

static constexpr int FIST_TRIANGLES = 46;

static const uint8_t EYE_CELLS[4] = {5, 6, 7, 8};

static const char* PART_BONES[TOTAL_PARTS] = {

    "", "Pelvis_Mantle", "Spine2", "Neck", "L_ShoulderArmor", "L_Pectoral", "Collar", "R_Shoulder", "R_Pectoral",

    "Spine2_Mantle", "L_Hip", "SpineArmor1", "Spine_Mantle", "R_Hip", "SpineArmor2", "L_Shoulder",

    "L_UpArmTwist", "L_Elbow", "L_ForeArmTwist", "L_ForeArmTwist1", "R_Elbow"

};

struct Vec3 {

    float x = 0.0f, y = 0.0f, z = 0.0f;

    Vec3 operator+(const Vec3& b) const { return {x + b.x, y + b.y, z + b.z}; }

    Vec3 operator-(const Vec3& b) const { return {x - b.x, y - b.y, z - b.z}; }

    Vec3 operator*(float s) const { return {x * s, y * s, z * s}; }

    float length() const { return std::sqrt(x * x + y * y + z * z); }

    float dist(const Vec3& b) const { return (*this - b).length(); }

    static Vec3 lerp(const Vec3& a, const Vec3& b, float t) {

        return {a.x + (b.x - a.x) * t, a.y + (b.y - a.y) * t, a.z + (b.z - a.z) * t};

    }

};

struct Quat {

    float x = 0.0f, y = 0.0f, z = 0.0f, w = 1.0f;

    static Quat identity() { return {0.0f, 0.0f, 0.0f, 1.0f}; }

    static Quat from_rotation_y(float a) {

        return {0.0f, std::sin(a * 0.5f), 0.0f, std::cos(a * 0.5f)};

    }

    Quat normalize() const {

        float l = std::sqrt(x * x + y * y + z * z + w * w);

        if (l < 1e-6f) return identity();

        return {x / l, y / l, z / l, w / l};

    }

    Quat inverse() const { return {-x, -y, -z, w}; }

    Quat operator*(const Quat& b) const {

        return {

            w * b.x + x * b.w + y * b.z - z * b.y,

            w * b.y - x * b.z + y * b.w + z * b.x,

            w * b.z + x * b.y - y * b.x + z * b.w,

            w * b.w - x * b.x - y * b.y - z * b.z

        };

    }

    Vec3 rotate(const Vec3& v) const {

        Vec3 qv = {x, y, z};

        Vec3 uv = {qv.y * v.z - qv.z * v.y, qv.z * v.x - qv.x * v.z, qv.x * v.y - qv.y * v.x};

        Vec3 uuv = {qv.y * uv.z - qv.z * uv.y, qv.z * uv.x - qv.x * uv.z, qv.x * uv.y - qv.y * uv.x};

        return v + (uv * w + uuv) * 2.0f;

    }

    static Quat slerp(const Quat& a, const Quat& b_in, float t) {

        Quat b = b_in;

        float dot = a.x * b.x + a.y * b.y + a.z * b.z + a.w * b.w;

        if (dot < 0.0f) {

            dot = -dot;

            b = {-b.x, -b.y, -b.z, -b.w};

        }

        if (dot > 0.9995f) {

            return Quat{a.x + (b.x - a.x) * t, a.y + (b.y - a.y) * t, a.z + (b.z - a.z) * t, a.w + (b.w - a.w) * t}.normalize();

        }

        float theta_0 = std::acos(std::clamp(dot, -1.0f, 1.0f));

        float theta = theta_0 * t;

        float sin_theta = std::sin(theta);

        float sin_theta_0 = std::sin(theta_0);

        float s0 = std::cos(theta) - dot * sin_theta / sin_theta_0;

        float s1 = sin_theta / sin_theta_0;

        return Quat{a.x * s0 + b.x * s1, a.y * s0 + b.y * s1, a.z * s0 + b.z * s1, a.w * s0 + b.w * s1}.normalize();

    }

    static Quat from_mat3(const float c0[3], const float c1[3], const float c2[3]) {

        float m00 = c0[0], m10 = c0[1], m20 = c0[2];

        float m01 = c1[0], m11 = c1[1], m21 = c1[2];

        float m02 = c2[0], m12 = c2[1], m22 = c2[2];

        float tr = m00 + m11 + m22;

        Quat q;

        if (tr > 0.0f) {

            float s = std::sqrt(tr + 1.0f) * 2.0f;

            q = {(m21 - m12) / s, (m02 - m20) / s, (m10 - m01) / s, 0.25f * s};

        } else if (m00 > m11 && m00 > m22) {

            float s = std::sqrt(1.0f + m00 - m11 - m22) * 2.0f;

            q = {0.25f * s, (m01 + m10) / s, (m02 + m20) / s, (m21 - m12) / s};

        } else if (m11 > m22) {

            float s = std::sqrt(1.0f + m11 - m00 - m22) * 2.0f;

            q = {(m01 + m10) / s, 0.25f * s, (m12 + m21) / s, (m02 - m20) / s};

        } else {

            float s = std::sqrt(1.0f + m22 - m00 - m11) * 2.0f;

            q = {(m02 + m20) / s, (m12 + m21) / s, 0.25f * s, (m10 - m01) / s};

        }

        return q.normalize();

    }

};

struct PartPose {

    Quat rot = Quat::identity();

    Vec3 pos = {0.0f, 0.0f, 0.0f};

    float scale = 1.0f;

};

struct PoseSet {

    PartPose parts[TOTAL_PARTS];

    bool valid = false;

};

static std::mutex g_LogMutex;

static FILE* g_LogFile = nullptr;

static void LogMsg(const char* fmt, ...) {

    std::lock_guard<std::mutex> lock(g_LogMutex);

    if (!g_LogFile) {

        g_LogFile = fopen("D:\\Modding\\MarioPhysics\\mario_physics.log", "w");

    }

    if (g_LogFile) {

        va_list args;

        va_start(args, fmt);

        vfprintf(g_LogFile, fmt, args);

        fprintf(g_LogFile, "\n");

        fflush(g_LogFile);

        va_end(args);

    }

}

static bool IsValidPtr(uintptr_t p, size_t len = 8) {

    if (p < 0x10000 || p > 0x7FFFFFFFFFFFULL || (p & 7ULL) != 0) return false;

    return !IsBadReadPtr((const void*)p, len);

}

static bool IsValidUnalignedPtr(uintptr_t p, size_t len = 8) {

    if (p < 0x10000 || p > 0x7FFFFFFFFFFFULL) return false;

    return !IsBadReadPtr((const void*)(p & ~7ULL), len + 8);

}


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
            "Local\\Mario64Telemetry"
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
        g_TelemetryLogFile = fopen("D:\\Modding\\MarioPhysics\\mario_telemetry.log", "w");
        if (g_TelemetryLogFile) {
            fprintf(g_TelemetryLogFile, "=== MARIO 64 PHYSICS TELEMETRY LOG INITIALIZED ===\n");
            fprintf(g_TelemetryLogFile, "[TIME_MS] [TAG       ] Details...\n");
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

    fprintf(g_TelemetryLogFile, "\n");
    fflush(g_TelemetryLogFile);
}

// --- Globals ---

static std::vector<uint8_t> g_RomBuffer;

static std::vector<uint8_t> g_TexAtlas(11 * 64 * 64 * 4);

static std::atomic<bool> g_Sm64Ready{false};

static std::atomic<uintptr_t> g_PlayerIns{0};

static std::mutex g_LivePosesMutex;

static std::mutex g_PoseMutex;

static PoseSet g_WorldCharPose;

static PoseSet g_MenuStandingPose;

// Track live hkaPose pointers that belong to Mario skeletons so we can reassert poses continuously

// Candidate skeletons seen by the sync hook while in the world (ptr, bone count, last seen tick)

struct PoseCandidate { uintptr_t pose; uint32_t bones; DWORD lastSeen; };

static constexpr int MAX_CANDIDATES = 64;

static PoseCandidate g_Candidates[MAX_CANDIDATES];

static int g_CandidateCount = 0;

// The player's own hkaPose, discovered at runtime (version independent)

static std::atomic<uintptr_t> g_PlayerHkaPose{0};

static void RememberCandidate(uintptr_t hkaPosePtr, uint32_t bones) {

    if (!hkaPosePtr) return;

    DWORD now = GetTickCount();

    std::lock_guard<std::mutex> lock(g_LivePosesMutex);

    for (int i = 0; i < g_CandidateCount; ++i) {

        if (g_Candidates[i].pose == hkaPosePtr) { g_Candidates[i].lastSeen = now; g_Candidates[i].bones = bones; return; }

    }

    if (g_CandidateCount < MAX_CANDIDATES) {

        g_Candidates[g_CandidateCount++] = {hkaPosePtr, bones, now};

    } else {

        // replace the stalest

        int oldest = 0;

        for (int i = 1; i < MAX_CANDIDATES; ++i) if (g_Candidates[i].lastSeen < g_Candidates[oldest].lastSeen) oldest = i;

        g_Candidates[oldest] = {hkaPosePtr, bones, now};

    }

}

// --- WaveOut 32kHz Audio ---

static HWAVEOUT g_WaveOut = nullptr;

static constexpr int NUM_AUDIO_BUFS = 16;

static constexpr int AUDIO_BUF_SAMPLES = 544 * 2 * 2;

static WAVEHDR g_WaveHdrs[NUM_AUDIO_BUFS];

static int16_t g_AudioData[NUM_AUDIO_BUFS][AUDIO_BUF_SAMPLES];

static int g_NextAudioBuf = 0;

static void InitWaveOutAudio() {

    WAVEFORMATEX wfx = {};

    wfx.wFormatTag = WAVE_FORMAT_PCM;

    wfx.nChannels = 2;

    wfx.nSamplesPerSec = 32000;

    wfx.wBitsPerSample = 16;

    wfx.nBlockAlign = 4;

    wfx.nAvgBytesPerSec = 32000 * 4;

    if (waveOutOpen(&g_WaveOut, WAVE_MAPPER, &wfx, 0, 0, CALLBACK_NULL) == MMSYSERR_NOERROR) {

        for (int i = 0; i < NUM_AUDIO_BUFS; ++i) {

            memset(&g_WaveHdrs[i], 0, sizeof(WAVEHDR));

            g_WaveHdrs[i].lpData = (LPSTR)g_AudioData[i];

            g_WaveHdrs[i].dwBufferLength = AUDIO_BUF_SAMPLES * sizeof(int16_t);

            waveOutPrepareHeader(g_WaveOut, &g_WaveHdrs[i], sizeof(WAVEHDR));

            g_WaveHdrs[i].dwFlags |= WHDR_DONE;

        }

        LogMsg("[AUDIO] waveOut 32000Hz Stereo inicializado com sucesso!");

    }

}

static void TickSM64Audio() {

    if (!g_WaveOut) return;

    uint32_t queuedSamples = 0;

    for (int i = 0; i < NUM_AUDIO_BUFS; ++i) {

        if (!(g_WaveHdrs[i].dwFlags & WHDR_DONE)) {

            queuedSamples += 544 * 2;

        }

    }

    WAVEHDR& hdr = g_WaveHdrs[g_NextAudioBuf];

    if (hdr.dwFlags & WHDR_DONE) {

        uint32_t n = sm64_audio_tick(queuedSamples, 1100, g_AudioData[g_NextAudioBuf]);

        if (n > 0) {

            hdr.dwBufferLength = n * 2 * 2 * sizeof(int16_t);

            hdr.dwFlags &= ~WHDR_DONE;

            waveOutWrite(g_WaveOut, &hdr, sizeof(WAVEHDR));

            g_NextAudioBuf = (g_NextAudioBuf + 1) % NUM_AUDIO_BUFS;

        }

    }

}

// --- Part Pose Math (Exact port of er-mario/src/engine_mario.rs) ---

static uint8_t ComputeEyeCell(const float* uv, uint16_t used) {

    std::vector<float> eyes;

    for (uint16_t t = 0; t < used; ++t) {

        float u0 = uv[t * 6 + 0], u1 = uv[t * 6 + 2], u2 = uv[t * 6 + 4];

        float mean = (u0 + u1 + u2) / 3.0f;

        float hi = std::max({u0, u1, u2});

        float lo = std::min({u0, u1, u2});

        if ((hi - lo) > 1e-4f && mean >= (5.0f / 11.0f) && mean < (9.0f / 11.0f)) {

            eyes.push_back(mean);

        }

    }

    if (eyes.empty()) return 5;

    std::sort(eyes.begin(), eyes.end());

    return (uint8_t)(eyes[eyes.size() / 2] * 11.0f);

}

static PoseSet ComputeRelativeParts(const float* mats, int count, const float marioPos[3], uint8_t eyeCell, bool peace) {

    PoseSet out;

    if (count < SM64_PARTS) return out;

    for (int i = 0; i < TOTAL_PARTS; ++i) {

        out.parts[i] = {Quat::identity(), {0.0f, 0.0f, 0.0f}, 1.0f};

    }

    for (int i = 1; i < SM64_PARTS; ++i) {

        const float* m = &mats[i * 16];

        float invScale = 1.0f / MODEL_SCALE;

        float c0[3] = {m[0] * invScale, m[1] * invScale, m[2] * invScale};

        float c1[3] = {m[4] * invScale, m[5] * invScale, m[6] * invScale};

        float c2[3] = {m[8] * invScale, m[9] * invScale, m[10] * invScale};

        float l0 = std::sqrt(c0[0]*c0[0] + c0[1]*c0[1] + c0[2]*c0[2]);

        float l1 = std::sqrt(c1[0]*c1[0] + c1[1]*c1[1] + c1[2]*c1[2]);

        float l2 = std::sqrt(c2[0]*c2[0] + c2[1]*c2[1] + c2[2]*c2[2]);

        float grow = (l0 + l1 + l2) / 3.0f;

        float sc = (std::isfinite(grow) && grow > 0.1f) ? grow : 1.0f;

        float invGrow = 1.0f / sc;

        float n0[3] = {c0[0]*invGrow, c0[1]*invGrow, c0[2]*invGrow};

        float n1[3] = {c1[0]*invGrow, c1[1]*invGrow, c1[2]*invGrow};

        float n2[3] = {c2[0]*invGrow, c2[1]*invGrow, c2[2]*invGrow};

        Quat q = Quat::from_mat3(n0, n1, n2);

        out.parts[i].rot = {q.x, -q.y, -q.z, q.w};

        out.parts[i].scale = sc;

        Vec3 t = {(m[12] - marioPos[0]) * SCALE_ER, (m[13] - marioPos[1]) * SCALE_ER, (m[14] - marioPos[2]) * SCALE_ER};

        out.parts[i].pos = {-t.x, t.y, t.z};

    }

    out.parts[PEACE_PART] = out.parts[RIGHT_HAND_PART];

    out.parts[PEACE_PART].scale = peace ? out.parts[RIGHT_HAND_PART].scale : 0.01f;

    if (peace) out.parts[RIGHT_HAND_PART].scale = 0.01f;

    Vec3 eyeTuck = {0.185f * 0.006f, -0.983f * 0.006f, 0.0f};

    PartPose head = out.parts[HEAD_PART];

    for (int k = 0; k < 4; ++k) {

        Vec3 pos = (EYE_CELLS[k] == eyeCell) ? head.pos : (head.pos + head.rot.rotate(eyeTuck));

        out.parts[SM64_PARTS + k] = {head.rot, pos, head.scale};

    }

    out.valid = true;

    return out;

}

static PoseSet ToCharacterSpace(const PoseSet& in, Quat charRot, float extraLiftY = 0.0f) {

    if (!in.valid) return in;

    PoseSet out = in;

    Quat inv = charRot.inverse();

    for (int i = 0; i < TOTAL_PARTS; ++i) {

        out.parts[i].rot = (inv * in.parts[i].rot).normalize();

        out.parts[i].pos = inv.rotate(in.parts[i].pos);

        out.parts[i].pos.y += extraLiftY;

        out.parts[i].scale = in.parts[i].scale;

    }

    return out;

}

static PoseSet BlendPoses(const PoseSet& a, const PoseSet& b, float t) {

    if (!a.valid) return b;

    if (!b.valid) return a;

    PoseSet out = b;

    for (int i = 0; i < TOTAL_PARTS; ++i) {

        if (a.parts[i].pos.dist(b.parts[i].pos) < 2.0f) {

            out.parts[i].pos = Vec3::lerp(a.parts[i].pos, b.parts[i].pos, t);

            out.parts[i].rot = Quat::slerp(a.parts[i].rot, b.parts[i].rot, t);

        }

    }

    return out;

}

// --- Skeleton Bone Mapping & Pose Writing (Fixed-size lock-free cache: never reallocates!) ---

struct CachedSkeleton {

    uintptr_t skeleton = 0;

    bool isMarioSkeleton = false;

    int bones[TOTAL_PARTS] = {0};

};

static std::mutex g_SkelMutex;

static constexpr int MAX_CACHED_SKELS = 128;

static CachedSkeleton g_SkelCache[MAX_CACHED_SKELS];

static std::atomic<int> g_SkelCacheCount{0};

static bool ValidateHkaPoseLayout(uintptr_t hkaPosePtr, uintptr_t& outSkel, uintptr_t& outLocal, uintptr_t& outModel, uintptr_t& outParents, uint32_t& outCount) {

    if (!IsValidPtr(hkaPosePtr, 0x30)) return false;

    uintptr_t skeleton = *(uintptr_t*)(hkaPosePtr + 0x00);

    uintptr_t local = *(uintptr_t*)(hkaPosePtr + 0x08);

    uint32_t localCount = *(uint32_t*)(hkaPosePtr + 0x10);

    uintptr_t model = *(uintptr_t*)(hkaPosePtr + 0x18);

    uint32_t modelCount = *(uint32_t*)(hkaPosePtr + 0x20);

    if (localCount < 25 || localCount > 512 || localCount != modelCount) return false;

    if (!IsValidPtr(skeleton, 0x40)) return false;

    uintptr_t parents = *(uintptr_t*)(skeleton + 0x20);

    uint32_t parentCount = *(uint32_t*)(skeleton + 0x28);

    uint32_t boneCount = *(uint32_t*)(skeleton + 0x38);

    if (parentCount != localCount || boneCount != localCount) return false;

    if (!IsValidPtr(local, localCount * 0x30) || !IsValidPtr(model, modelCount * 0x30)) return false;

    if (!IsValidUnalignedPtr(parents, localCount * 2)) return false;

    outSkel = skeleton;

    outLocal = local;

    outModel = model;

    outParents = parents;

    outCount = localCount;

    return true;

}

static const CachedSkeleton* GetOrMapSkeleton(uintptr_t skeleton, uint32_t count) {

    int curCount = g_SkelCacheCount.load(std::memory_order_acquire);

    for (int i = 0; i < curCount; ++i) {

        if (g_SkelCache[i].skeleton == skeleton) {

            return &g_SkelCache[i];

        }

    }

    std::lock_guard<std::mutex> lock(g_SkelMutex);

    curCount = g_SkelCacheCount.load(std::memory_order_relaxed);

    for (int i = 0; i < curCount; ++i) {

        if (g_SkelCache[i].skeleton == skeleton) {

            return &g_SkelCache[i];

        }

    }

    if (curCount >= MAX_CACHED_SKELS) return nullptr;

    uintptr_t namesPtr = *(uintptr_t*)(skeleton + 0x30);

    if (!IsValidPtr(namesPtr, count * 16)) return nullptr;

    CachedSkeleton cs;

    cs.skeleton = skeleton;

    cs.isMarioSkeleton = true;

    cs.bones[0] = 0;

    for (int i = 1; i < TOTAL_PARTS; ++i) {

        cs.bones[i] = -1;

        size_t targetLen = strlen(PART_BONES[i]);

        for (uint32_t b = 0; b < count; ++b) {

            uintptr_t strPtr = (*(uintptr_t*)(namesPtr + b * 16)) & ~1ULL;

            if (IsValidUnalignedPtr(strPtr, 36)) {

                const char* bname = (const char*)strPtr;

                if (strncmp(bname, PART_BONES[i], targetLen) == 0 && bname[targetLen] == '\0') {

                    cs.bones[i] = (int)b;

                    break;

                }

            }

        }

        if (cs.bones[i] < 0) {

            cs.isMarioSkeleton = false;

            break;

        }

    }

    g_SkelCache[curCount] = cs;

    g_SkelCacheCount.store(curCount + 1, std::memory_order_release);

    if (cs.isMarioSkeleton) {

        LogMsg("[ENGINE-MARIO] Esqueleto mapeado com sucesso: %p (%u ossos)", (void*)skeleton, count);

    }

    return &g_SkelCache[curCount];

}

static void WritePoseToHkaPose(uintptr_t local, uintptr_t model, uintptr_t parents, uint32_t count, const int bones[TOTAL_PARTS], const PoseSet& pose, bool away) {

    if (!pose.valid || count == 0 || count > 512) return;

    auto readQs = [](uintptr_t base, uint32_t b, Vec3& outPos, Quat& outRot) {

        const float* v = (const float*)(base + b * 0x30);

        outPos = {v[0], v[1], v[2]};

        outRot = Quat{v[4], v[5], v[6], v[7]}.normalize();

    };

    auto writeQs = [](uintptr_t base, uint32_t b, const Vec3& p, const Quat& r, float s) {

        float* v = (float*)(base + b * 0x30);

        v[0] = p.x; v[1] = p.y; v[2] = p.z; v[3] = 0.0f;

        v[4] = r.x; v[5] = r.y; v[6] = r.z; v[7] = r.w;

        v[8] = s;   v[9] = s;   v[10] = s;  v[11] = 0.0f;

    };

    bool hasPinned[512] = {false};

    PartPose pinned[512];

    bool keep[512] = {false};

    const int16_t* parentArr = (const int16_t*)parents;

    for (int i = 1; i < TOTAL_PARTS; ++i) {

        int b = bones[i];

        if (b < 0 || (uint32_t)b >= count) continue;

        hasPinned[b] = true;

        pinned[b] = pose.parts[i];

        int cur = b;

        while (cur >= 0 && (uint32_t)cur < count && !keep[cur]) {

            keep[cur] = true;

            cur = parentArr[cur];

        }

    }

    Vec3 worldPos[512];

    Quat worldRot[512];

    for (uint32_t b = 0; b < count; ++b) {

        int16_t p = parentArr[b];

        Vec3 parPos = (p >= 0 && (uint32_t)p < b) ? worldPos[p] : Vec3{0.0f, 0.0f, 0.0f};

        Quat parRot = (p >= 0 && (uint32_t)p < b) ? worldRot[p] : Quat::identity();

        float scale = hasPinned[b] ? pinned[b].scale : (keep[b] ? 1.0f : 0.0f);

        Vec3 mPos;

        Quat mRot;

        if (hasPinned[b]) {

            mPos = pinned[b].pos;

            mRot = pinned[b].rot;

            Quat invPar = parRot.inverse();

            Vec3 lPos = invPar.rotate(mPos - parPos);

            Quat lRot = (invPar * mRot).normalize();

            writeQs(local, b, lPos, lRot, scale);

        } else if (keep[b]) {

            Vec3 lPos; Quat lRot;

            readQs(local, b, lPos, lRot);

            mPos = parPos + parRot.rotate(lPos);

            mRot = (parRot * lRot).normalize();

        } else {

            Vec3 lPos; Quat lRot;

            readQs(local, b, lPos, lRot);

            if (away && (p < 0 || keep[p])) {

                lPos.y -= 1000.0f;

            }

            writeQs(local, b, lPos, lRot, 0.0f);

            mPos = parPos + parRot.rotate(lPos);

            mRot = (parRot * lRot).normalize();

        }

        writeQs(model, b, mPos, mRot, scale);

        worldPos[b] = mPos;

        worldRot[b] = mRot;

    }

}

// --- Hook hkaPose::syncModelSpace (Runs for EVERY skeleton sync in Character Creation AND Open World!) ---

typedef void (*SyncModelSpace_t)(uintptr_t hkaPosePtr);

static SyncModelSpace_t Original_SyncModelSpace = nullptr;

static void Detour_SyncModelSpace(uintptr_t hkaPosePtr) {

    Original_SyncModelSpace(hkaPosePtr);

    if (!g_Sm64Ready.load(std::memory_order_relaxed)) return;

    uintptr_t skel = 0, local = 0, model = 0, parents = 0;

    uint32_t count = 0;

    if (!ValidateHkaPoseLayout(hkaPosePtr, skel, local, model, parents, count)) return;

    const CachedSkeleton* cs = GetOrMapSkeleton(skel, count);

    if (!cs || !cs->isMarioSkeleton) return;

    uintptr_t playerIns = g_PlayerIns.load(std::memory_order_relaxed);

    if (!playerIns) {

        // Character creation / menus: every Mario-bone skeleton stands in the menu pose

        PoseSet pose;

        {

            std::lock_guard<std::mutex> lock(g_PoseMutex);

            pose = g_MenuStandingPose;

        }

        WritePoseToHkaPose(local, model, parents, count, cs->bones, pose, true);

        return;

    }

    // In the world: only the player's own skeleton is posed (NPCs share the bone names!)

    RememberCandidate(hkaPosePtr, count);

    bool isPlayer = false;

    uintptr_t cached = g_PlayerHkaPose.load(std::memory_order_relaxed);

    if (cached != 0 && cached == hkaPosePtr) {

        isPlayer = true;

    } else if (IsValidPtr(playerIns, 0x400)) {

        uintptr_t imp = *(uintptr_t*)(playerIns + 0x398);

        if (imp && (imp + 0x48) == hkaPosePtr) {

            isPlayer = true;

            g_PlayerHkaPose.store(hkaPosePtr, std::memory_order_relaxed);

            LogMsg("[WORLD] hkaPose do jogador detectado via playerIns+0x398: %p (%u ossos)", (void*)hkaPosePtr, count);

        }

    }

    if (isPlayer) {

        PoseSet pose;

        {

            std::lock_guard<std::mutex> lock(g_PoseMutex);

            pose = g_WorldCharPose;

        }

        WritePoseToHkaPose(local, model, parents, count, cs->bones, pose, false);

    }

}

// --- Controller Interception (Zero left stick for Elden Ring so Mario owns movement) ---

typedef DWORD (WINAPI *pfn_XInputGetState)(DWORD dwUserIndex, XINPUT_STATE* pState);

static pfn_XInputGetState Original_XInputGetState = nullptr;

static XINPUT_STATE g_RawPad = {};

static bool g_PadCaptured = false;

static DWORD WINAPI Detour_XInputGetState(DWORD dwUserIndex, XINPUT_STATE* pState) {

    if (!Original_XInputGetState) return ERROR_DEVICE_NOT_CONNECTED;

    DWORD res = Original_XInputGetState(dwUserIndex, pState);

    if (res == ERROR_SUCCESS && pState && dwUserIndex == 0) {

        g_RawPad = *pState;

        g_PadCaptured = true;

        if (g_PlayerIns.load(std::memory_order_relaxed) != 0) {
            // Left stick belongs to Mario: zero it out for Elden Ring so Souls controller stays idle
            pState->Gamepad.sThumbLX = 0;
            pState->Gamepad.sThumbLY = 0;
        }

    }

    return res;

}

// --- Havok Raycasting for Wall and Ground Environment Collision ---
struct alignas(16) HavokPosition {
    float x = 0.0f;
    float y = 0.0f;
    float z = 0.0f;
    float w = 0.0f;
};

static bool CastRayER(uintptr_t exeBase, uintptr_t playerIns, const Vec3& from, const Vec3& delta, Vec3& hitPos, uint32_t filter = 0x2000058) {
    if (!exeBase || !playerIns || !IsValidPtr(playerIns, 0x200)) return false;

        uintptr_t modBag = *(uintptr_t*)(playerIns + 0x190);
        if (!IsValidPtr(modBag, 0x80)) return false;

        uintptr_t physMod = *(uintptr_t*)(modBag + 0x68);
        if (!IsValidPtr(physMod, 0x100)) return false;

        uintptr_t chrProxy = *(uintptr_t*)(physMod + 0x98);
        if (!IsValidPtr(chrProxy, 0x20)) return false;

        void* physWorld = *(void**)(chrProxy + 0x18);
        if (!physWorld || !IsValidPtr((uintptr_t)physWorld, 0x10)) return false;

        if (*(uintptr_t*)((uintptr_t)physWorld + 8) == 0) return false;

        alignas(16) HavokPosition start = {from.x, from.y, from.z, 0.0f};
        alignas(16) HavokPosition ext   = {delta.x, delta.y, delta.z, 0.0f};
        alignas(16) HavokPosition outHit = {};

        typedef bool (*FnCastRay)(void* physWorld, uint32_t filter, const HavokPosition* start, const HavokPosition* delta, HavokPosition* outHit, void* owner);
        FnCastRay castRay = (FnCastRay)(exeBase + 0xc70090);

        bool hit = castRay(physWorld, filter, &start, &ext, &outHit, (void*)playerIns);
        if (hit) {
            hitPos = {outHit.x, outHit.y, outHit.z};
            return true;
        }
        return false;

}

static bool CastWallRay(uintptr_t exeBase, uintptr_t playerIns, const Vec3& from, const Vec3& delta, Vec3& hitPoint, uint32_t* outFilter = nullptr) {
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
}

// --- Camera Forward Scanner (Finds horizontal forward vector from ChrCam in WorldChrMan) ---

static Vec3 GetCameraForward(uintptr_t worldChrManPtr, const Vec3& fallbackDir) {

    if (!worldChrManPtr || !IsValidPtr(worldChrManPtr, 8)) return fallbackDir;

    uintptr_t wcm = *(uintptr_t*)worldChrManPtr;

    if (!wcm || !IsValidPtr(wcm, 0x20000)) return fallbackDir;

    static uintptr_t s_CachedCamOffset = 0;

    if (s_CachedCamOffset) {

        uintptr_t camPtr = *(uintptr_t*)(wcm + s_CachedCamOffset);

        if (IsValidPtr(camPtr, 0x50)) {

            const float* m = (const float*)(camPtr + 0x10);

            Vec3 fwd = {m[8], m[9], m[10]};

            Vec3 horiz = {fwd.x, 0.0f, fwd.z};

            float hlen = horiz.length();

            if (hlen > 0.01f) return horiz * (1.0f / hlen);

        }

        s_CachedCamOffset = 0;

    }

    for (uintptr_t off = 0x1E000; off < 0x20000; off += 8) {

        uintptr_t camPtr = *(uintptr_t*)(wcm + off);

        if (IsValidPtr(camPtr, 0x50)) {

            const float* m = (const float*)(camPtr + 0x10);

            float len_r = m[0]*m[0] + m[1]*m[1] + m[2]*m[2];

            float len_u = m[4]*m[4] + m[5]*m[5] + m[6]*m[6];

            float len_f = m[8]*m[8] + m[9]*m[9] + m[10]*m[10];

            if (std::abs(len_r - 1.0f) < 0.08f && std::abs(len_u - 1.0f) < 0.08f && std::abs(len_f - 1.0f) < 0.08f) {

                s_CachedCamOffset = off;

                Vec3 fwd = {m[8], m[9], m[10]};

                Vec3 horiz = {fwd.x, 0.0f, fwd.z};

                float hlen = horiz.length();

                if (hlen > 0.01f) return horiz * (1.0f / hlen);

            }

        }

    }

    return fallbackDir;

}

// --- Memory Scanner ---

static uintptr_t ScanPattern(uintptr_t base, size_t size, const uint8_t* pat, const char* mask) {

    size_t patLen = strlen(mask);

    const uint8_t* data = (const uint8_t*)base;

    for (size_t i = 0; i + patLen <= size; ++i) {

        bool ok = true;

        for (size_t j = 0; j < patLen; ++j) {

            if (mask[j] == 'x' && data[i + j] != pat[j]) {

                ok = false;

                break;

            }

        }

        if (ok) return base + i;

    }

    return 0;

}

static uintptr_t FindWorldChrMan(uintptr_t base, size_t size) {

    const uint8_t pat[] = {0x48, 0x8B, 0x05, 0x00, 0x00, 0x00, 0x00, 0x48, 0x85, 0xC0, 0x74, 0x0F, 0x48, 0x39, 0x88};

    uintptr_t addr = ScanPattern(base, size, pat, "xxx????xxxxxxxx");

    if (!addr) return 0;

    int32_t rel = *(int32_t*)(addr + 3);

    return addr + 7 + rel;

}

static uintptr_t GetPlayerIns(uintptr_t worldChrManPtr) {

    if (!worldChrManPtr || !IsValidPtr(worldChrManPtr, 8)) return 0;

    uintptr_t wcm = *(uintptr_t*)worldChrManPtr;

    if (!wcm || !IsValidPtr(wcm, 0x20000)) return 0;

    uintptr_t offsets[] = {0x1E508, 0x10EF8};

    for (uintptr_t off : offsets) {

        uintptr_t p = *(uintptr_t*)(wcm + off);

        if (IsValidPtr(p, 0x400)) {

            uintptr_t modBag = *(uintptr_t*)(p + 0x190);

            if (IsValidPtr(modBag, 0x80)) {

                uintptr_t phys = *(uintptr_t*)(modBag + 0x68);

                if (IsValidPtr(phys, 0x200)) return p;

            }

        }

    }

    return 0;

}

// --- Combat Hit Detection & Damage ---

static void DealMarioCombatDamage(uintptr_t worldChrManPtr, uintptr_t playerIns, const Vec3& playerErPos, const SM64MarioState& state) {

    bool isGroundPound = (state.action == 0x008008A9 || state.action == 0x0080023C);

    bool isPunch = (state.flags & 0x00100000) != 0;

    bool isKick  = (state.flags & 0x00200000) != 0;

    bool isTrip  = (state.flags & 0x00400000) != 0;

    bool isDive  = (state.action == 0x0188088A || state.action == 0x01880888 || state.action == 0x00880456);

    bool isSlide = (state.action == 0x0180088C || state.action == 0x0080045A);

    bool isAttackingAction = (state.action & 0x00800000) != 0;

    bool isStomp = ((state.action & 0x00000800) != 0 && state.velocity[1] < -2.0f);

    bool isAttacking = isPunch || isKick || isTrip || isDive || isSlide || isGroundPound || isAttackingAction || isStomp;

    if (!isAttacking) return;

    static DWORD lastHitTick = 0;

    DWORD now = GetTickCount();

    if (now - lastHitTick < 200) return;

    if (!worldChrManPtr || !IsValidPtr(worldChrManPtr, 8)) return;

    uintptr_t wcm = *(uintptr_t*)worldChrManPtr;

    if (!wcm || !IsValidPtr(wcm, 0x20000)) return;

    float baseReach = isGroundPound ? 4.8f : (isDive ? 3.8f : 3.0f);

    bool hitAny = false;

    // Scan all 196 ChrSets in WorldChrMan (from offset 0x1DED8 to 0x1E4F8)

    for (uintptr_t setOff = 0x1DED8; setOff < 0x1E4F8; setOff += 8) {

        uintptr_t chrSet = *(uintptr_t*)(wcm + setOff);

        if (!IsValidPtr(chrSet, 0x20)) continue;

        uint32_t capacity = *(uint32_t*)(chrSet + 0x10);

        if (capacity == 0 || capacity > 1024) continue;

        uintptr_t entries = *(uintptr_t*)(chrSet + 0x18);

        if (!IsValidPtr(entries, (size_t)capacity * 16)) continue;

        for (uint32_t i = 0; i < capacity; ++i) {

            uintptr_t entry = entries + (uintptr_t)i * 16;

            uintptr_t chr = *(uintptr_t*)entry;

            if (!chr || chr == playerIns || !IsValidPtr(chr, 0x200)) continue;

            // Skip friendly team types: player(1), allies(2, 5, 12), and invisible helpers(0)

            uint8_t team = *(uint8_t*)(chr + 0x6C);

            if (team == 0 || team == 1 || team == 2 || team == 5 || team == 12) continue;

            uintptr_t modBag = *(uintptr_t*)(chr + 0x190);

            if (!IsValidPtr(modBag, 0x80)) continue;

            uintptr_t dataMod = *(uintptr_t*)(modBag + 0x00);

            uintptr_t physMod = *(uintptr_t*)(modBag + 0x68);

            if (!IsValidPtr(dataMod, 0x180) || !IsValidPtr(physMod, 0x100)) continue;

            int32_t hp = *(int32_t*)(dataMod + 0x138);

            int32_t maxHp = *(int32_t*)(dataMod + 0x13C);

            if (hp <= 0 || maxHp <= 0) continue;

            Vec3 ePos = {*(float*)(physMod + 0x70), *(float*)(physMod + 0x74), *(float*)(physMod + 0x78)};

            float dy = std::fabs(ePos.y - playerErPos.y);

            if (dy > 4.5f) continue;

            float enemyRadius = 0.5f;

            if (IsValidPtr(physMod, 0x300)) {

                float r = *(float*)(physMod + 0x2F4);

                if (std::isfinite(r) && r > 0.2f && r < 8.0f) {

                    enemyRadius = r;

                }

            }

            float dist = std::sqrt((ePos.x - playerErPos.x)*(ePos.x - playerErPos.x) + (ePos.z - playerErPos.z)*(ePos.z - playerErPos.z));

            if (dist <= (baseReach + enemyRadius)) {

                int32_t dmg = 0;

                if (isGroundPound) {

                    dmg = std::max(150, (int32_t)(maxHp * 0.20f));

                } else if (isKick || isTrip) {

                    dmg = std::max(80, (int32_t)(maxHp * 0.12f));

                } else {

                    dmg = std::max(55, (int32_t)(maxHp * 0.08f));

                }

                if (maxHp > 3000) {

                    // Boss scaling: solid punch damage

                    dmg = isGroundPound ? 320 : (isKick ? 180 : 120);

                }

                int32_t newHp = std::max(0, hp - dmg);

                *(int32_t*)(dataMod + 0x138) = newHp;

                // Also damage super armor / poise

                uintptr_t armorMod = *(uintptr_t*)(modBag + 0x40);

                if (IsValidPtr(armorMod, 0x30)) {

                    float curSa = *(float*)(armorMod + 0x10);

                    float maxSa = *(float*)(armorMod + 0x14);

                    if (curSa > 0.0f && maxSa > 0.0f) {

                        float poiseDmg = isGroundPound ? 45.0f : (isKick ? 25.0f : 15.0f);

                        float newSa = std::max(0.0f, curSa - poiseDmg);

                        *(float*)(armorMod + 0x10) = newSa;

                        if (newSa <= 0.0f) {

                            LogMsg("[COMBAT] POISE BREAK no inimigo/boss %p!", (void*)chr);

                        }

                    }

                }

                lastHitTick = now;

                hitAny = true;

                // Classic SM64 impact sound (0x312F0081)

                sm64_play_sound_global(0x312F0081);

                g_EnemiesHitCount++;
                LogTelemetryEvent("COMBAT", "Mario HIT enemy %p (HP %d->%d, -%d)", (void*)chr, hp, newHp, dmg);
                LogMsg("[COMBAT] Mario ACERTOU inimigo/boss %p (cId=%u, team=%u)! Dist=%.2f (raio=%.2f), HP: %d/%d -> %d (-%d)",

                       (void*)chr, *(uint32_t*)(chr + 0x188), (unsigned)team, dist, enemyRadius, hp, maxHp, newHp, dmg);

                break;

            }

        }

        if (hitAny) break;

    }

}

// Diagnostics removed

// --- Main Thread ---

static DWORD WINAPI MainLoopThread(LPVOID) {

    timeBeginPeriod(1);
    InitTelemetry();

    LogMsg("[INIT] Inicializando ER Mario (libsm64 nativo + ROM N64)...");

    Sleep(2000);

    HMODULE hExe = GetModuleHandleW(nullptr);

    MODULEINFO modInfo = {};

    GetModuleInformation(GetCurrentProcess(), hExe, &modInfo, sizeof(modInfo));

    uintptr_t exeBase = (uintptr_t)modInfo.lpBaseOfDll;

    size_t exeSize = modInfo.SizeOfImage;

    // 1. Load ROM

    const char* romPaths[] = {

        "D:\\Modding\\Super Mario 64 (Europe) (En,Fr,De).z64",

        "D:\\Modding\\Super Mario 64 (USA).z64",

        "D:\\Modding\\sm64.z64"

    };

    for (const char* rp : romPaths) {

        FILE* f = fopen(rp, "rb");

        if (f) {

            fseek(f, 0, SEEK_END);

            size_t sz = ftell(f);

            fseek(f, 0, SEEK_SET);

            if (sz == 8 * 1024 * 1024) {

                g_RomBuffer.resize(sz);

                fread(g_RomBuffer.data(), 1, sz, f);

                LogMsg("[ROM] Carregada com sucesso: %s (%zu bytes, regiao='%c')", rp, sz, (char)g_RomBuffer[0x3E]);

            }

            fclose(f);

            if (!g_RomBuffer.empty()) break;

        }

    }

    if (g_RomBuffer.empty()) {

        LogMsg("[ERRO] ROM do Super Mario 64 nao encontrada em D:\\Modding!");

        return 0;

    }

    // 2. Init libsm64 & Audio

    sm64_global_init(g_RomBuffer.data(), g_TexAtlas.data());

    sm64_audio_init(g_RomBuffer.data());

    InitWaveOutAudio();

    // Solid flat floor at Y=0 within SM64 LEVEL_BOUNDARY_MAX (0x2000 = 8192)

    // Elden Ring Havok handles world floor/walls; SM64 handles character moveset & physics

    const int32_t E = 4000;

    SM64Surface floors[2] = {};

    floors[0].vertices[0][0] = -E; floors[0].vertices[0][1] = 0; floors[0].vertices[0][2] = -E;

    floors[0].vertices[1][0] =  E; floors[0].vertices[1][1] = 0; floors[0].vertices[1][2] =  E;

    floors[0].vertices[2][0] =  E; floors[0].vertices[2][1] = 0; floors[0].vertices[2][2] = -E;

    floors[1].vertices[0][0] = -E; floors[1].vertices[0][1] = 0; floors[1].vertices[0][2] = -E;

    floors[1].vertices[1][0] = -E; floors[1].vertices[1][1] = 0; floors[1].vertices[1][2] =  E;

    floors[1].vertices[2][0] =  E; floors[1].vertices[2][1] = 0; floors[1].vertices[2][2] =  E;

    sm64_static_surfaces_load(floors, 2);

    int32_t marioId = sm64_mario_create(0.0f, 0.0f, 0.0f);

    LogMsg("[SM64] Mario criado! marioId = %d", marioId);

    if (marioId < 0) {

        LogMsg("[ERRO] Falha ao criar instancia do Mario no libsm64!");

        return 0;

    }

    std::vector<float> geoPos(SM64_GEO_MAX_TRIANGLES * 9);

    std::vector<float> geoNorm(SM64_GEO_MAX_TRIANGLES * 9);

    std::vector<float> geoCol(SM64_GEO_MAX_TRIANGLES * 9);

    std::vector<float> geoUv(SM64_GEO_MAX_TRIANGLES * 6);

    SM64MarioGeometryBuffers geoBufs = {geoPos.data(), geoNorm.data(), geoCol.data(), geoUv.data(), 0};

    std::vector<float> partMats(64 * 16);

    std::vector<int> triParts(SM64_GEO_MAX_TRIANGLES);

    SM64MarioInputs inputs = {};

    SM64MarioState state = {};

    sm64_er_mute(1);

    for (int i = 0; i < 30; ++i) {

        sm64_mario_tick(marioId, &inputs, &state, &geoBufs);

    }

    sm64_er_mute(0);

    int pCount = sm64_er_get_parts(partMats.data(), triParts.data(), nullptr, nullptr);

    PoseSet initRel = ComputeRelativeParts(partMats.data(), pCount, state.position, 5, false);

    LogMsg("[SM64] Pose inicial extraida: pCount=%d, valid=%d, tris=%u", pCount, (int)initRel.valid, (unsigned)geoBufs.numTrianglesUsed);

    {

        std::lock_guard<std::mutex> lock(g_PoseMutex);

        g_MenuStandingPose = ToCharacterSpace(initRel, Quat::from_rotation_y(PI_F));

        g_WorldCharPose = g_MenuStandingPose;

    }

    g_Sm64Ready.store(true, std::memory_order_release);

    // 3. Hook hkaPose::syncModelSpace

    MH_Initialize();

    const uint8_t syncSig[] = {0x48, 0x83, 0xEC, 0x18, 0x80, 0x79, 0x38, 0x00, 0x0F, 0x85};

    uintptr_t syncAddr = ScanPattern(exeBase, exeSize, syncSig, "xxxxxxxxxx");

    if (syncAddr) {

        if (MH_CreateHook((LPVOID)syncAddr, (LPVOID)&Detour_SyncModelSpace, (LPVOID*)&Original_SyncModelSpace) == MH_OK) {

            MH_EnableHook((LPVOID)syncAddr);

            LogMsg("[HOOK] hkaPose::syncModelSpace hookado em %p (RVA +0x%zx)!", (void*)syncAddr, syncAddr - exeBase);

        }

    } else {

        LogMsg("[AVISO] Assinatura de hkaPose::syncModelSpace nao encontrada!");

    }

    HMODULE hX = GetModuleHandleW(L"xinput1_4.dll");

    if (!hX) hX = GetModuleHandleW(L"xinput1_3.dll");

    if (!hX) hX = LoadLibraryW(L"xinput1_4.dll");

    if (hX) {

        void* pProc = (void*)GetProcAddress(hX, "XInputGetState");

        if (pProc) {

            if (MH_CreateHook(pProc, (LPVOID)&Detour_XInputGetState, (LPVOID*)&Original_XInputGetState) == MH_OK) {

                MH_EnableHook(pProc);

                LogMsg("[HOOK] XInputGetState hookado com sucesso!");

            }

        }

    }

    uintptr_t worldChrManPtr = FindWorldChrMan(exeBase, exeSize);
    LogMsg("[SCAN] WorldChrMan = %p", (void*)worldChrManPtr);

    PoseSet prevPose = initRel;
    PoseSet currPose = initRel;
    Vec3 origin = {0.0f, 0.0f, 0.0f};
    Vec3 currentErPos = {0.0f, 0.0f, 0.0f};
    float lastSafeGroundY = 0.0f;
    bool worldInitialized = false;
    uintptr_t loggedPlayerIns = 0;

    LARGE_INTEGER freq, lastCounter;
    QueryPerformanceFrequency(&freq);
    QueryPerformanceCounter(&lastCounter);
    float accum = 0.0f;
    constexpr float SM64_DT = 1.0f / 30.0f;

    while (true) {
        LARGE_INTEGER nowCounter;
        QueryPerformanceCounter(&nowCounter);
        float dt = (float)(nowCounter.QuadPart - lastCounter.QuadPart) / (float)freq.QuadPart;
        lastCounter = nowCounter;
        if (dt > 0.1f) dt = 0.1f;
        accum += dt;

        uintptr_t playerIns = GetPlayerIns(worldChrManPtr);
        g_PlayerIns.store(playerIns, std::memory_order_relaxed);

        if (!playerIns) {
            worldInitialized = false;
            // Tick Menu Mario at 30Hz so he breathes and blinks in Character Creation
            while (accum >= SM64_DT) {
                accum -= SM64_DT;
                SM64MarioInputs mInp = {};
                sm64_er_mute(1);
                sm64_mario_tick(marioId, &mInp, &state, &geoBufs);
                sm64_er_mute(0);
                int cnt = sm64_er_get_parts(partMats.data(), triParts.data(), nullptr, nullptr);
                uint8_t eye = ComputeEyeCell(geoUv.data(), geoBufs.numTrianglesUsed);
                prevPose = currPose;
                currPose = ComputeRelativeParts(partMats.data(), cnt, state.position, eye, false);
            }
            float alpha = std::clamp(accum / SM64_DT, 0.0f, 1.0f);
            PoseSet blended = BlendPoses(prevPose, currPose, alpha);
            {
                std::lock_guard<std::mutex> lock(g_PoseMutex);
                g_MenuStandingPose = ToCharacterSpace(blended, Quat::from_rotation_y(PI_F));
            }
            Sleep(4);
            continue;
        }

        // Open World Active!
        // Discover the player's own hkaPose
        {
            static DWORD lastScan = 0;
            static DWORD worldSince = 0;
            uintptr_t curImp = 0;
            if (IsValidPtr(playerIns, 0x400)) {
                curImp = *(uintptr_t*)(playerIns + 0x398);
            }
            static uintptr_t lastLoggedImp = 0;
            if (playerIns != loggedPlayerIns || curImp != lastLoggedImp) {
                loggedPlayerIns = playerIns;
                lastLoggedImp = curImp;
                g_PlayerHkaPose.store(0, std::memory_order_relaxed);
                worldSince = GetTickCount();
                lastScan = 0;
            }
            DWORD nowT = GetTickCount();
            if (g_PlayerHkaPose.load(std::memory_order_relaxed) == 0 && nowT - lastScan > 250) {
                lastScan = nowT;
                PoseCandidate cands[MAX_CANDIDATES];
                int nc = 0;
                {
                    std::lock_guard<std::mutex> lock(g_LivePosesMutex);
                    nc = g_CandidateCount;
                    for (int i = 0; i < nc; ++i) cands[i] = g_Candidates[i];
                }
                uintptr_t found = 0;
                if (IsValidPtr(playerIns, 0x2000)) {
                    for (int i = 0; i < nc && !found; ++i) {
                        if (nowT - cands[i].lastSeen > 500) continue;
                        uintptr_t imp = cands[i].pose - 0x48;
                        for (uintptr_t off = 0; off < 0x2000; off += 8) {
                            if (*(uintptr_t*)(playerIns + off) == imp) {
                                found = cands[i].pose;
                                LogMsg("[WORLD] hkaPose do jogador identificado: %p (%u ossos) via playerIns+0x%zx", (void*)found, cands[i].bones, off);
                                break;
                            }
                        }
                    }
                }
                if (!found && nowT - worldSince > 4000) {
                    uint32_t best = 0;
                    for (int i = 0; i < nc; ++i) {
                        if (nowT - cands[i].lastSeen > 500) continue;
                        if (cands[i].bones > best) { best = cands[i].bones; found = cands[i].pose; }
                    }
                    if (found) {
                        LogMsg("[WORLD] AVISO: importer nao achado em playerIns; usando o maior esqueleto vivo %p (%u ossos)", (void*)found, best);
                    }
                }
                if (found) g_PlayerHkaPose.store(found, std::memory_order_relaxed);
            }
        }

        uintptr_t modBag = *(uintptr_t*)(playerIns + 0x190);
        if (!IsValidPtr(modBag, 0x80)) {
            Sleep(2);
            continue;
        }
        uintptr_t dataMod = *(uintptr_t*)(modBag + 0x00);
        uintptr_t physMod = *(uintptr_t*)(modBag + 0x68);
        if (!IsValidPtr(physMod, 0x200) || !IsValidPtr(dataMod, 0x200)) {
            Sleep(2);
            continue;
        }

        Vec3 erPos = {*(float*)(physMod + 0x70), *(float*)(physMod + 0x74), *(float*)(physMod + 0x78)};
        Quat erRot = {*(float*)(physMod + 0x50), *(float*)(physMod + 0x54), *(float*)(physMod + 0x58), *(float*)(physMod + 0x5C)};

        // Reject loading screens, menus, respawns, or dummy coordinates (0, 0, 1.04)
        bool isDummyLoadingCoord = (std::abs(erPos.x) < 0.001f && std::abs(erPos.z) < 0.001f && std::abs(erPos.y) < 1.50f);
        bool inWorldCoords = (std::abs(erPos.x) < 50000.0f && std::abs(erPos.z) < 50000.0f && 
                              std::abs(erPos.y) < 5000.0f && !isDummyLoadingCoord);
        if (!inWorldCoords) {
            worldInitialized = false;
            Sleep(8);
            continue;
        }

        // Initialize Mario once real world coordinates are loaded
        if (!worldInitialized) {
            origin = erPos;
            currentErPos = erPos;
            lastSafeGroundY = erPos.y;
            sm64_set_mario_position(marioId, 0.0f, 0.0f, 0.0f);
            sm64_set_mario_velocity(marioId, 0.0f, 0.0f, 0.0f);
            sm64_set_mario_health(marioId, 0x0880);
            worldInitialized = true;
            LogMsg("[WORLD] Jogador entrou no mundo em (%.2f, %.2f, %.2f)! Origin fixada.", erPos.x, erPos.y, erPos.z);
        }

        // Detect fast travel / teleports: re-center origin smoothly
        if (worldInitialized) {
            float warpDist = erPos.dist(currentErPos);
            if (warpDist > 30.0f) {
                origin = erPos;
                currentErPos = erPos;
                lastSafeGroundY = erPos.y;
                sm64_set_mario_position(marioId, 0.0f, 0.0f, 0.0f);
                sm64_set_mario_velocity(marioId, 0.0f, 0.0f, 0.0f);
                state.position[0] = 0.0f;
                state.position[1] = 0.0f;
                state.position[2] = 0.0f;
                LogMsg("[WORLD] Teleporte detectado (dist=%.2f m)! Re-centrado.", warpDist);
            }
        }

        // Gather Inputs (Keyboard + Mouse + XInput Gamepad)
        float stickX = 0.0f, stickY = 0.0f;
        bool rawAttack = false;
        bool rawJump = false;
        bool rawZ = false;
        bool rawDodge = false;

        // Controller input (from hooked XInput or direct fallback)
        XINPUT_STATE xst = {};
        bool hasPad = false;
        if (g_PadCaptured) {
            xst = g_RawPad;
            hasPad = true;
        } else if (XInputGetState(0, &xst) == ERROR_SUCCESS) {
            hasPad = true;
        }

        static WORD s_PrevButtons = 0;
        if (hasPad) {
            float lx = xst.Gamepad.sThumbLX / 32768.0f;
            float ly = xst.Gamepad.sThumbLY / 32768.0f;
            float mag = std::sqrt(lx * lx + ly * ly);
            if (mag > 0.15f) {
                stickX = lx;
                stickY = -ly; // SM64: negative Y is forward
            }

            WORD justPressed = xst.Gamepad.wButtons & (~s_PrevButtons);
            s_PrevButtons = xst.Gamepad.wButtons;

            if (xst.Gamepad.wButtons & XINPUT_GAMEPAD_A) rawJump = true;
            if ((justPressed & (XINPUT_GAMEPAD_RIGHT_SHOULDER | XINPUT_GAMEPAD_X)) || (xst.Gamepad.bRightTrigger > 100)) rawAttack = true;
            if (justPressed & XINPUT_GAMEPAD_B) rawDodge = true;

            // Z is held (LT or LB), releases immediately when unpressed
            if ((xst.Gamepad.wButtons & (XINPUT_GAMEPAD_LEFT_THUMB | XINPUT_GAMEPAD_LEFT_SHOULDER)) || (xst.Gamepad.bLeftTrigger > 100)) {
                rawZ = true;
            }
        }

        // Keyboard & Mouse input
        if (GetAsyncKeyState('W') & 0x8000) stickY -= 1.0f;
        if (GetAsyncKeyState('S') & 0x8000) stickY += 1.0f;
        if (GetAsyncKeyState('A') & 0x8000) stickX -= 1.0f;
        if (GetAsyncKeyState('D') & 0x8000) stickX += 1.0f;
        float klen = std::sqrt(stickX * stickX + stickY * stickY);
        if (klen > 1.0f) {
            stickX /= klen;
            stickY /= klen;
        }
        if ((GetAsyncKeyState(VK_SPACE) & 0x8000) || (GetAsyncKeyState('F') & 0x8000)) rawJump = true;
        if (GetAsyncKeyState(VK_LBUTTON) & 0x8000) rawAttack = true;
        if ((GetAsyncKeyState('C') & 0x8000) || (GetAsyncKeyState('X') & 0x8000) ||
            (GetAsyncKeyState(VK_CONTROL) & 0x8000)) {
            rawZ = true;
        }
        if ((GetAsyncKeyState(VK_SHIFT) & 0x8000) || (GetAsyncKeyState(VK_MENU) & 0x8000)) {
            rawDodge = true;
        }

        // Latch quick button taps between 30Hz ticks
        static bool s_AttackLatched = false;
        static bool s_JumpLatched = false;
        static bool s_DodgeLatched = false;
        static bool s_ZLatched = false;
        if (rawAttack) s_AttackLatched = true;
        if (rawJump) s_JumpLatched = true;
        if (rawDodge) s_DodgeLatched = true;
        if (rawZ) s_ZLatched = true;

        float qn = std::sqrt(erRot.x*erRot.x + erRot.y*erRot.y + erRot.z*erRot.z + erRot.w*erRot.w);
        if (!(qn > 0.9f && qn < 1.1f)) erRot = Quat::identity();
        Vec3 facing = erRot.rotate({0.0f, 0.0f, -1.0f});
        Vec3 dir = {facing.x, 0.0f, facing.z};
        float dirLen = dir.length();
        if (dirLen > 1e-4f) {
            dir = dir * (1.0f / dirLen);
        } else {
            dir = {0.0f, 0.0f, 1.0f};
        }

        while (accum >= SM64_DT) {
            accum -= SM64_DT;
            prevPose = currPose;

            bool attackPressed = s_AttackLatched || rawAttack;
            s_AttackLatched = false;
            bool jumpPressed = s_JumpLatched || rawJump;
            s_JumpLatched = false;
            bool dodgePressed = s_DodgeLatched || rawDodge;
            s_DodgeLatched = false;
            bool zPressed = s_ZLatched || rawZ;
            s_ZLatched = false;

            // Keep Mario full health & immortal so he NEVER dies from fall damage in SM64
            sm64_set_mario_health(marioId, 0x0880);

            // Never let death/cutscene animations lock Mario
            if ((state.action & 0x000001C0) == 0x00000100 /* ACT_GROUP_CUTSCENE */ || state.health < 0x100) {
                sm64_set_mario_action(marioId, 0x0C400201 /* ACT_IDLE */);
                sm64_set_mario_health(marioId, 0x0880);
            }

            bool isAirborne = (state.action & 0x00000800) != 0;
            bool inPunchAction = (state.action == 0x00800380 || state.action == 0x00800457);
            float slen = std::sqrt(stickX * stickX + stickY * stickY);

            // Rollout from dive slide on jump press:
            if ((state.action == 0x00880456 /* ACT_DIVE_SLIDE */ || state.action == 0x00000386 /* ACT_STOMACH_SLIDE_STOP */) && jumpPressed) {
                sm64_set_mario_action(marioId, 0x010008A6 /* ACT_FORWARD_ROLLOUT */);
                jumpPressed = false;
            }

            // Release crouch instantly when Z is released:
            bool isCrouchAction = (state.action == 0x0C008220 /* ACT_CROUCHING */ ||
                                   state.action == 0x0C008221 /* ACT_START_CROUCHING */ ||
                                   state.action == 0x04000443 /* ACT_START_CRAWLING */ ||
                                   state.action == 0x04000444 /* ACT_CRAWLING */);
            if (!zPressed && isCrouchAction) {
                sm64_set_mario_action(marioId, 0x0C400201 /* ACT_IDLE */);
            }

            static uint8_t s_LastSentB = 0;
            uint8_t btnB = 0;

            if (dodgePressed && slen > 0.2f && !isAirborne) {
                // Dodge while moving = Mario's signature Dive & Rollout!
                btnB = 1;
            } else if (attackPressed) {
                // 3-hit punch combo: pulse B button
                btnB = (inPunchAction && s_LastSentB == 1) ? 0 : 1;
            }
            s_LastSentB = btnB;

            uint8_t btnA = jumpPressed ? 1 : 0;
            uint8_t btnZ = zPressed ? 1 : 0;

            // Camera horizontal forward vector
            Vec3 camFwd = GetCameraForward(worldChrManPtr, dir);
            inputs.camLookX = -camFwd.x;
            inputs.camLookZ = camFwd.z;

            inputs.stickX = stickX;
            inputs.stickY = stickY;

            // Attack on ground: dampen stick to guarantee 3-hit punch combo instead of dive
            if (btnB && !isAirborne && !dodgePressed) {
                inputs.stickX *= 0.2f;
                inputs.stickY *= 0.2f;
            } else if (inPunchAction && !isAirborne) {
                inputs.stickX = 0.0f;
                inputs.stickY = 0.0f;
            }

            inputs.buttonA = btnA;
            inputs.buttonB = btnB;
            inputs.buttonZ = btnZ;

            sm64_mario_tick(marioId, &inputs, &state, &geoBufs);
            TickSM64Audio();

            // --- TELEMETRY: Action State Changes ---
            static uint32_t s_LastAction = 0;
            static uint32_t s_ActionDurationTicks = 0;
            if (state.action != s_LastAction) {
                float hSpeed = std::sqrt(state.velocity[0]*state.velocity[0] + state.velocity[2]*state.velocity[2]);
                LogTelemetryEvent("ACTION", "%s (0x%08X) -> %s (0x%08X) | ER=(%.2f, %.2f, %.2f) hSpd=%.2f vSpd=%.2f air=%d dur=%uticks",
                    GetSM64ActionName(s_LastAction), s_LastAction,
                    GetSM64ActionName(state.action), state.action,
                    currentErPos.x, currentErPos.y, currentErPos.z,
                    hSpeed, state.velocity[1], isAirborne ? 1 : 0, s_ActionDurationTicks);
                s_LastAction = state.action;
                s_ActionDurationTicks = 0;
            } else {
                s_ActionDurationTicks++;
            }

            int cnt = sm64_er_get_parts(partMats.data(), triParts.data(), nullptr, nullptr);
            int rightHandTris = 0;
            for (uint16_t t = 0; t < geoBufs.numTrianglesUsed; ++t) {
                if (triParts[t] == RIGHT_HAND_PART) rightHandTris++;
            }
            bool peace = (rightHandTris > FIST_TRIANGLES);
            uint8_t eye = ComputeEyeCell(geoUv.data(), geoBufs.numTrianglesUsed);
            currPose = ComputeRelativeParts(partMats.data(), cnt, state.position, eye, peace);

            // Calculate target world position from SM64
            Vec3 targetErPos;
            targetErPos.x = origin.x - state.position[0] * SCALE_ER; // mirrored on X
            targetErPos.y = origin.y + state.position[1] * SCALE_ER; // Y is up
            targetErPos.z = origin.z + state.position[2] * SCALE_ER; // Z is forward

            // --- 1. ENVIRONMENT WALLS, DOORS & PROPS COLLISION ---
            constexpr float PLAYER_RADIUS = 0.35f;
            Vec3 moveDelta = targetErPos - currentErPos;
            float horizMove = std::sqrt(moveDelta.x * moveDelta.x + moveDelta.z * moveDelta.z);

            Vec3 finalTarget = targetErPos;
            bool hitWall = false;
            uint32_t hitWallLayer = 0;
            float hitWallDist = 0.0f;
            Vec3 hitWallPos = {};

            if (horizMove > 0.0005f) {
                // Test at 3 heights: ankle (0.25m), waist/doorhandle (0.85m), and head (1.45m)
                float rayHeights[3] = {currentErPos.y + 0.25f, currentErPos.y + 0.85f, currentErPos.y + 1.45f};

                // A. Direct Forward Sweep along moveDelta (blocks doors and angled walls)
                Vec3 fwdDir = {moveDelta.x / horizMove, 0.0f, moveDelta.z / horizMove};
                float probeDistFwd = horizMove + PLAYER_RADIUS;
                Vec3 rayDeltaFwd = {fwdDir.x * probeDistFwd, 0.0f, fwdDir.z * probeDistFwd};

                for (float h : rayHeights) {
                    Vec3 hitPoint;
                    uint32_t layer = 0;
                    Vec3 rayStart = {currentErPos.x, h, currentErPos.z};
                    if (CastWallRay(exeBase, playerIns, rayStart, rayDeltaFwd, hitPoint, &layer)) {
                        float distToHit = std::sqrt((hitPoint.x - currentErPos.x)*(hitPoint.x - currentErPos.x) + 
                                                    (hitPoint.z - currentErPos.z)*(hitPoint.z - currentErPos.z));
                        if (distToHit <= probeDistFwd) {
                            hitWall = true;
                            hitWallLayer = layer;
                            hitWallDist = distToHit;
                            hitWallPos = hitPoint;
                            float allowed = std::max(0.0f, distToHit - PLAYER_RADIUS);
                            finalTarget.x = currentErPos.x + fwdDir.x * allowed;
                            finalTarget.z = currentErPos.z + fwdDir.z * allowed;
                            break;
                        }
                    }
                }

                // B. Separate X and Z sweeps for smooth sliding along wall and door surfaces
                if (!hitWall) {
                    if (std::abs(moveDelta.x) > 0.0002f) {
                        float signX = (moveDelta.x > 0.0f) ? 1.0f : -1.0f;
                        float probeDistX = std::abs(moveDelta.x) + PLAYER_RADIUS;
                        Vec3 rayDeltaX = {signX * probeDistX, 0.0f, 0.0f};

                        for (float h : rayHeights) {
                            Vec3 hitPoint;
                            uint32_t layer = 0;
                            Vec3 rayStart = {currentErPos.x, h, currentErPos.z};
                            if (CastWallRay(exeBase, playerIns, rayStart, rayDeltaX, hitPoint, &layer)) {
                                float distToHit = std::abs(hitPoint.x - currentErPos.x);
                                if (distToHit <= probeDistX) {
                                    hitWall = true;
                                    hitWallLayer = layer;
                                    hitWallDist = distToHit;
                                    hitWallPos = hitPoint;
                                    float allowedX = std::max(0.0f, distToHit - PLAYER_RADIUS);
                                    finalTarget.x = currentErPos.x + signX * allowedX;
                                    break;
                                }
                            }
                        }
                    }

                    if (std::abs(moveDelta.z) > 0.0002f) {
                        float signZ = (moveDelta.z > 0.0f) ? 1.0f : -1.0f;
                        float probeDistZ = std::abs(moveDelta.z) + PLAYER_RADIUS;
                        Vec3 rayDeltaZ = {0.0f, 0.0f, signZ * probeDistZ};

                        for (float h : rayHeights) {
                            Vec3 hitPoint;
                            uint32_t layer = 0;
                            Vec3 rayStart = {finalTarget.x, h, currentErPos.z};
                            if (CastWallRay(exeBase, playerIns, rayStart, rayDeltaZ, hitPoint, &layer)) {
                                float distToHit = std::abs(hitPoint.z - currentErPos.z);
                                if (distToHit <= probeDistZ) {
                                    hitWall = true;
                                    hitWallLayer = layer;
                                    hitWallDist = distToHit;
                                    hitWallPos = hitPoint;
                                    float allowedZ = std::max(0.0f, distToHit - PLAYER_RADIUS);
                                    finalTarget.z = currentErPos.z + signZ * allowedZ;
                                    break;
                                }
                            }
                        }
                    }
                }

                if (hitWall) {
                    targetErPos.x = finalTarget.x;
                    targetErPos.z = finalTarget.z;

                    // Sync clamped coordinates back to libsm64 so Mario slides along walls and doors
                    float sm64_x = -(targetErPos.x - origin.x) / SCALE_ER;
                    float sm64_z =  (targetErPos.z - origin.z) / SCALE_ER;
                    sm64_set_mario_position(marioId, sm64_x, state.position[1], sm64_z);
                    state.position[0] = sm64_x;
                    state.position[2] = sm64_z;

                    LogTelemetryEvent("WALL_HIT", "Blocked by Layer 0x%X (dist=%.2fm, hitPt=(%.2f,%.2f,%.2f))",
                        hitWallLayer, hitWallDist, hitWallPos.x, hitWallPos.y, hitWallPos.z);
                }
            }

            // --- 2. CEILING COLLISION (PREVENTS POPPING THROUGH ROOFS/ATTICS) ---
            bool hitCeil = false;
            Vec3 ceilHitPos = {};
            bool nowAirborne = (state.action & 0x00000800) != 0;
            if (nowAirborne && state.velocity[1] > 0.0f) {
                Vec3 ceilStart = {currentErPos.x, currentErPos.y + 0.80f, currentErPos.z};
                Vec3 ceilDelta = {0.0f, 2.00f, 0.0f};
                Vec3 ceilHit;
                uint32_t ceilLayer = 0;
                if (CastWallRay(exeBase, playerIns, ceilStart, ceilDelta, ceilHit, &ceilLayer)) {
                    float maxAllowedY = ceilHit.y - 1.40f;
                    if (targetErPos.y > maxAllowedY) {
                        hitCeil = true;
                        ceilHitPos = ceilHit;
                        float prevTargetY = targetErPos.y;
                        targetErPos.y = maxAllowedY;
                        // Bonk head on ceiling and fall back down!
                        sm64_set_mario_velocity(marioId, state.velocity[0], -6.0f, state.velocity[2]);
                        LogTelemetryEvent("CEILING_HIT", "Bonked ceiling (Layer 0x%X) at Y=%.2fm | TargetY was %.2f -> Clamped to %.2fm",
                            ceilLayer, ceilHit.y, prevTargetY, maxAllowedY);
                    }
                }
            }

            // --- 3. ENVIRONMENT GROUND & LEDGE/CLIFF DETECTION ---
            Vec3 groundStart = {targetErPos.x, currentErPos.y + 1.20f, targetErPos.z};
            Vec3 groundDelta = {0.0f, -40.0f, 0.0f}; // Probe deep into world (40m)
            Vec3 groundHit;
            uint32_t hitGroundLayer = 0;
            bool groundFound = CastRayER(exeBase, playerIns, groundStart, groundDelta, groundHit, 0x1704);
            if (groundFound) hitGroundLayer = 0x1704;
            if (!groundFound) {
                groundFound = CastRayER(exeBase, playerIns, groundStart, groundDelta, groundHit, 0x08);
                if (groundFound) hitGroundLayer = 0x08;
            }
            if (!groundFound) {
                groundFound = CastRayER(exeBase, playerIns, groundStart, groundDelta, groundHit, 0x2000058);
                if (groundFound) hitGroundLayer = 0x2000058;
            }
            if (!groundFound && IsValidPtr(physMod, 0x2c0)) {
                float capY = *(float*)(physMod + 0x2a4);
                if (std::abs(capY - currentErPos.y) < 3.0f && capY > 1.0f) {
                    groundHit = {targetErPos.x, capY, targetErPos.z};
                    groundFound = true;
                    hitGroundLayer = 0xCA9501E; // Havok capsule contact fallback
                }
            }

            if (groundFound) {
                lastSafeGroundY = groundHit.y;
            }

            if (nowAirborne) {
                // Airborne (Jumping / Long Jump / Dive / Freefall / Ground Pound):
                *(uint8_t*)(physMod + 0x1d5) = 1; // gravity_disabled = true

                // Check landing: if Mario has descended to or below the real terrain surface
                if (groundFound && state.velocity[1] <= 0.0f && targetErPos.y <= groundHit.y + 0.08f) {
                    targetErPos.y = groundHit.y;
                    origin.y = groundHit.y;
                    sm64_set_mario_position(marioId, state.position[0], 0.0f, state.position[2]);
                    state.position[1] = 0.0f;
                    LogTelemetryEvent("LANDING", "Landed at Y=%.2fm (Layer 0x%X) | dropDist=%.2fm",
                        groundHit.y, hitGroundLayer, currentErPos.y - groundHit.y);
                }

                *(float*)(physMod + 0x70) = targetErPos.x;
                *(float*)(physMod + 0x74) = targetErPos.y;
                *(float*)(physMod + 0x78) = targetErPos.z;
                *(uint8_t*)(physMod + 0x91) = 1;  // chr_proxy_pos_update_requested = true
            } else {
                // Grounded:
                if (groundFound) {
                    float dropDist = currentErPos.y - groundHit.y;
                    if (dropDist > 0.60f) {
                        // Ground dropped significantly: Mario walked off a roof, cliff, or ledge!
                        // Trigger authentic SM64 freefall so he falls down naturally instead of walking in thin air
                        sm64_set_mario_action(marioId, 0x0100088C /* ACT_FREEFALL */);
                        origin.y = groundHit.y;
                        float smHeight = std::min(4000.0f, (currentErPos.y - groundHit.y) / SCALE_ER);
                        sm64_set_mario_position(marioId, state.position[0], smHeight, state.position[2]);
                        state.position[1] = smHeight;
                        *(uint8_t*)(physMod + 0x1d5) = 1; // gravity_disabled = true while falling
                        LogTelemetryEvent("LEDGE_DROP", "Walked off cliff/roof! CurrY=%.2f GndY=%.2f (dropDist=+%.2fm) -> ACT_FREEFALL",
                            currentErPos.y, groundHit.y, dropDist);
                    } else if (dropDist >= -1.25f) {
                        float stepDelta = groundHit.y - currentErPos.y;
                        if (std::abs(stepDelta) > 0.06f) {
                            LogTelemetryEvent("STEP", "Stair/Slope step: CurrY=%.2f -> NewY=%.2f (delta=%+.2fm) [Layer 0x%X]",
                                currentErPos.y, groundHit.y, stepDelta, hitGroundLayer);
                        }
                        // Smooth step up or down stairs, ramps, and slopes up to 1.25m
                        targetErPos.y = groundHit.y;
                        origin.y = groundHit.y;
                    }
                }

                *(uint8_t*)(physMod + 0x1d0) = 0; // is_falling = false
                *(uint8_t*)(physMod + 0x1d1) = 1; // is_touching_ground = true
                *(uint8_t*)(physMod + 0x92) = 1;  // standing_on_solid_ground = true
                *(uint8_t*)(physMod + 0x93) = 1;  // touching_solid_ground = true

                *(float*)(physMod + 0x70) = targetErPos.x;
                *(float*)(physMod + 0x74) = targetErPos.y;
                *(float*)(physMod + 0x78) = targetErPos.z;
                *(uint8_t*)(physMod + 0x91) = 1;  // chr_proxy_pos_update_requested = true
            }

            currentErPos = targetErPos;

            // Character rotation follows Mario's face angle
            Quat q = Quat::from_rotation_y(PI_F - state.faceAngle);
            *(float*)(physMod + 0x50) = q.x;
            *(float*)(physMod + 0x54) = q.y;
            *(float*)(physMod + 0x58) = q.z;
            *(float*)(physMod + 0x5C) = q.w;

            // Re-centre SM64 coordinate space when traveling beyond 25m
            if (std::abs(state.position[0]) > 2500.0f || std::abs(state.position[2]) > 2500.0f) {
                origin = targetErPos;
                currentErPos = targetErPos;
                sm64_set_mario_position(marioId, 0.0f, state.position[1], 0.0f);
                state.position[0] = 0.0f;
                state.position[2] = 0.0f;
            }

            // --- TELEMETRY: Heartbeat & Shared Memory Live State ---
            g_TelemetryTickCount++;
            if (g_TelemetryTickCount % 30 == 0) {
                float hSpeed = std::sqrt(state.velocity[0]*state.velocity[0] + state.velocity[2]*state.velocity[2]);
                LogTelemetryEvent("HEARTBEAT", "ER=(%.2f, %.2f, %.2f) Act=%s (0x%08X) hSpd=%.2f vSpd=%.2f GndY=%.2f Drop=%+.2fm Air=%d Inp=[Stk:(%+.2f,%+.2f) A=%d B=%d Z=%d]",
                    currentErPos.x, currentErPos.y, currentErPos.z,
                    GetSM64ActionName(state.action), state.action,
                    hSpeed, state.velocity[1],
                    groundFound ? groundHit.y : -999.0f,
                    groundFound ? (currentErPos.y - groundHit.y) : 0.0f,
                    nowAirborne ? 1 : 0,
                    inputs.stickX, inputs.stickY, inputs.buttonA, inputs.buttonB, inputs.buttonZ);
            }

            if (g_pTelemetryShm) {
                g_pTelemetryShm->tickCount = g_TelemetryTickCount;
                g_pTelemetryShm->timeMs = timeGetTime();
                g_pTelemetryShm->erX = currentErPos.x;
                g_pTelemetryShm->erY = currentErPos.y;
                g_pTelemetryShm->erZ = currentErPos.z;
                g_pTelemetryShm->faceAngle = state.faceAngle;
                g_pTelemetryShm->originX = origin.x;
                g_pTelemetryShm->originY = origin.y;
                g_pTelemetryShm->originZ = origin.z;
                g_pTelemetryShm->sm64X = state.position[0];
                g_pTelemetryShm->sm64Y = state.position[1];
                g_pTelemetryShm->sm64Z = state.position[2];
                g_pTelemetryShm->velX = state.velocity[0];
                g_pTelemetryShm->velY = state.velocity[1];
                g_pTelemetryShm->velZ = state.velocity[2];
                g_pTelemetryShm->horizSpeed = std::sqrt(state.velocity[0]*state.velocity[0] + state.velocity[2]*state.velocity[2]);
                g_pTelemetryShm->vertSpeed = state.velocity[1];
                g_pTelemetryShm->action = state.action;
                g_pTelemetryShm->prevAction = s_LastAction;
                g_pTelemetryShm->actionTimer = s_ActionDurationTicks;
                strncpy(g_pTelemetryShm->actionName, GetSM64ActionName(state.action), sizeof(g_pTelemetryShm->actionName) - 1);
                g_pTelemetryShm->actionName[sizeof(g_pTelemetryShm->actionName) - 1] = '\0';
                g_pTelemetryShm->isAirborne = nowAirborne ? 1 : 0;
                g_pTelemetryShm->isGrounded = !nowAirborne ? 1 : 0;
                g_pTelemetryShm->stickX = inputs.stickX;
                g_pTelemetryShm->stickY = inputs.stickY;
                g_pTelemetryShm->btnA = inputs.buttonA;
                g_pTelemetryShm->btnB = inputs.buttonB;
                g_pTelemetryShm->btnZ = inputs.buttonZ;
                g_pTelemetryShm->padConnected = hasPad ? 1 : 0;
                g_pTelemetryShm->groundFound = groundFound ? 1 : 0;
                g_pTelemetryShm->groundY = groundFound ? groundHit.y : -999.0f;
                g_pTelemetryShm->dropDist = groundFound ? (currentErPos.y - groundHit.y) : 0.0f;
                g_pTelemetryShm->groundLayer = hitGroundLayer;
                g_pTelemetryShm->wallHit = hitWall ? 1 : 0;
                g_pTelemetryShm->wallHitDist = hitWallDist;
                g_pTelemetryShm->wallHitX = hitWallPos.x;
                g_pTelemetryShm->wallHitY = hitWallPos.y;
                g_pTelemetryShm->wallHitZ = hitWallPos.z;
                g_pTelemetryShm->wallLayer = hitWallLayer;
                g_pTelemetryShm->ceilingHit = hitCeil ? 1 : 0;
                g_pTelemetryShm->ceilingY = hitCeil ? ceilHitPos.y : -999.0f;
                g_pTelemetryShm->health = state.health;
                g_pTelemetryShm->enemiesHitCount = g_EnemiesHitCount.load(std::memory_order_relaxed);
            }

            // Combat damage against enemies and bosses
            DealMarioCombatDamage(worldChrManPtr, playerIns, targetErPos, state);
        }

        // Keep stamina full so player can jump and attack infinitely with Mario
        int32_t maxSp = *(int32_t*)(dataMod + 0x158);
        if (maxSp > 0) *(int32_t*)(dataMod + 0x154) = maxSp;

        float alpha = std::clamp(accum / SM64_DT, 0.0f, 1.0f);
        PoseSet blended = BlendPoses(prevPose, currPose, alpha);
        Quat q = Quat::from_rotation_y(PI_F - state.faceAngle);
        PoseSet charPose = ToCharacterSpace(blended, q, 0.0f);
        {
            std::lock_guard<std::mutex> lock(g_PoseMutex);
            g_WorldCharPose = charPose;
        }

        Sleep(1);
    }
    return 0;
}


BOOL APIENTRY DllMain(HMODULE hModule, DWORD ul_reason_for_call, LPVOID) {

    if (ul_reason_for_call == DLL_PROCESS_ATTACH) {

        DisableThreadLibraryCalls(hModule);

        CreateThread(nullptr, 0, MainLoopThread, nullptr, 0, nullptr);

    }

    return TRUE;

}
