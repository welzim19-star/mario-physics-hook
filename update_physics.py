import os

src_path = r"D:\Modding\MarioPhysics\src\dll_main.cpp"
with open(src_path, "r", encoding="utf-8") as f:
    text = f.read()

# 1. Add Detour_XInputGetState and GetCameraForward before "// --- Memory Scanner ---"
marker1 = "// --- Memory Scanner ---"
insert1 = """// --- Controller Interception (Zero left stick for Elden Ring so Mario owns movement) ---
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

// --- Memory Scanner ---"""
assert marker1 in text, "marker1 not found"
text = text.replace(marker1, insert1, 1)

# 2. Hook XInputGetState in MainLoopThread
marker2 = """    if (syncAddr) {
        if (MH_CreateHook((LPVOID)syncAddr, (LPVOID)&Detour_SyncModelSpace, (LPVOID*)&Original_SyncModelSpace) == MH_OK) {
            MH_EnableHook((LPVOID)syncAddr);
            LogMsg("[HOOK] hkaPose::syncModelSpace hookado em %p (RVA +0x%zx)!", (void*)syncAddr, syncAddr - exeBase);
        }
    } else {
        LogMsg("[AVISO] Assinatura de hkaPose::syncModelSpace nao encontrada!");
    }"""

insert2 = marker2 + """

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
    }"""
assert marker2 in text, "marker2 not found"
text = text.replace(marker2, insert2, 1)

# 3. Variables in MainLoopThread
old_vars = """    PoseSet prevPose = initRel;
    PoseSet currPose = initRel;
    float prevSmY = 0.0f;
    float currSmY = 0.0f;
    float groundErY = 0.0f;
    Vec3 lastErPos = {0.0f, 0.0f, 0.0f};
    bool worldInitialized = false;
    uintptr_t loggedPlayerIns = 0;"""

new_vars = """    PoseSet prevPose = initRel;
    PoseSet currPose = initRel;
    Vec3 origin = {0.0f, 0.0f, 0.0f};
    Vec3 lastErPos = {0.0f, 0.0f, 0.0f};
    bool worldInitialized = false;
    uintptr_t loggedPlayerIns = 0;"""
assert old_vars in text, "old_vars not found"
text = text.replace(old_vars, new_vars, 1)

# 4. Movement, Inputs, Tick, and Position update
old_loop_chunk = """        Vec3 erPos = {*(float*)(physMod + 0x70), *(float*)(physMod + 0x74), *(float*)(physMod + 0x78)};
        Quat erRot = {*(float*)(physMod + 0x50), *(float*)(physMod + 0x54), *(float*)(physMod + 0x58), *(float*)(physMod + 0x5C)};

        // Wait until the map finishes streaming in (non-zero position)
        if (!worldInitialized && (std::abs(erPos.x) + std::abs(erPos.y) + std::abs(erPos.z) > 1.0f)) {
            groundErY = erPos.y;
            lastErPos = erPos;
            sm64_set_mario_position(marioId, 0.0f, 0.0f, 0.0f);
            sm64_set_mario_velocity(marioId, 0.0f, 0.0f, 0.0f);
            sm64_set_mario_health(marioId, 0x0880);
            prevSmY = 0.0f;
            currSmY = 0.0f;
            worldInitialized = true;
            LogMsg("[WORLD] Jogador entrou no mundo em (%.2f, %.2f, %.2f)!", erPos.x, erPos.y, erPos.z);
        }

        // Gather Inputs (Keyboard + Mouse + XInput Controller)
        float stickX = 0.0f, stickY = 0.0f;
        bool rawAttack = false;
        bool rawJump = false;
        bool rawZ = false;
        bool rawDodge = false;

        // Keyboard & Mouse
        if (GetAsyncKeyState('W') & 0x8000) stickY -= 1.0f;
        if (GetAsyncKeyState('S') & 0x8000) stickY += 1.0f;
        if (GetAsyncKeyState('A') & 0x8000) stickX -= 1.0f;
        if (GetAsyncKeyState('D') & 0x8000) stickX += 1.0f;
        if ((GetAsyncKeyState(VK_SPACE) & 0x8000) || (GetAsyncKeyState('F') & 0x8000)) rawJump = true;
        if (GetAsyncKeyState(VK_LBUTTON) & 0x8000) rawAttack = true;
        if ((GetAsyncKeyState('C') & 0x8000) || (GetAsyncKeyState('X') & 0x8000) ||
            (GetAsyncKeyState(VK_CONTROL) & 0x8000)) {
            rawZ = true;
        }
        if ((GetAsyncKeyState(VK_SHIFT) & 0x8000) || (GetAsyncKeyState(VK_MENU) & 0x8000)) {
            rawDodge = true;
        }

        // XInput Gamepad (Xbox / DualShock / Generic)
        XINPUT_STATE xst = {};
        if (XInputGetState(0, &xst) == ERROR_SUCCESS) {
            float lx = xst.Gamepad.sThumbLX / 32768.0f;
            float ly = xst.Gamepad.sThumbLY / 32768.0f;
            if (std::sqrt(lx*lx + ly*ly) > 0.2f) {
                stickX = lx;
                stickY = -ly;
            }
            if (xst.Gamepad.wButtons & XINPUT_GAMEPAD_A) rawJump = true;
            if ((xst.Gamepad.wButtons & XINPUT_GAMEPAD_RIGHT_SHOULDER) || (xst.Gamepad.bRightTrigger > 100)) rawAttack = true;
            if (xst.Gamepad.wButtons & XINPUT_GAMEPAD_B) rawDodge = true;
            if ((xst.Gamepad.wButtons & (XINPUT_GAMEPAD_LEFT_THUMB | XINPUT_GAMEPAD_LEFT_SHOULDER)) || (xst.Gamepad.bLeftTrigger > 100)) {
                rawZ = true;
            }
        }

        // Latch button presses between 30Hz ticks
        static bool s_AttackLatched = false;
        static bool s_JumpLatched = false;
        static bool s_DodgeLatched = false;
        static bool s_ZLatched = false;
        if (rawAttack) s_AttackLatched = true;
        if (rawJump) s_JumpLatched = true;
        if (rawDodge) s_DodgeLatched = true;
        if (rawZ) s_ZLatched = true;

        float slen = std::clamp(std::sqrt(stickX * stickX + stickY * stickY), 0.0f, 1.0f);

        // Character's forward vector in Elden Ring (from er-mario: Quat * (0, 0, -1))
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
        float erFaceAngle = std::atan2(-dir.x, dir.z);

        while (accum >= SM64_DT) {
            accum -= SM64_DT;
            prevSmY = currSmY;

            // Measure horizontal movement speed in Elden Ring
            float horizDist = std::sqrt((erPos.x - lastErPos.x)*(erPos.x - lastErPos.x) + (erPos.z - lastErPos.z)*(erPos.z - lastErPos.z));
            lastErPos = erPos;
            bool movingInEr = (horizDist > 0.015f) || (slen > 0.1f);

            // Sync Mario's facing with the character's facing in Elden Ring
            sm64_set_mario_faceangle(marioId, erFaceAngle);

            bool attackPressed = s_AttackLatched || rawAttack;
            s_AttackLatched = false;
            bool jumpPressed = s_JumpLatched || rawJump;
            s_JumpLatched = false;
            bool dodgePressed = s_DodgeLatched || rawDodge;
            s_DodgeLatched = false;
            bool zPressed = s_ZLatched || rawZ;
            s_ZLatched = false;

            bool isAirborne = (state.action & 0x00000800) != 0;
            bool inPunchAction = (state.action == 0x00800380 || state.action == 0x00800457);

            static uint8_t s_LastSentB = 0;
            uint8_t btnB = 0;

            if (dodgePressed && movingInEr && !isAirborne) {
                // Dodge while moving = Mario's signature Dive & Rollout!
                btnB = 1;
            } else if (attackPressed) {
                // If Mario is currently punching, pulse 0 then 1 so libsm64 detects B_PRESSED for combo
                if (inPunchAction && s_LastSentB == 1) {
                    btnB = 0;
                } else {
                    btnB = 1;
                }
            }
            s_LastSentB = btnB;

            uint8_t btnA = jumpPressed ? 1 : 0;
            uint8_t btnZ = zPressed ? 1 : 0;

            inputs.camLookX = -dir.x;
            inputs.camLookZ = dir.z;
            inputs.stickX = 0.0f;

            if (dodgePressed && movingInEr && !isAirborne) {
                inputs.stickY = -1.0f; // full forward speed for Dive
            } else if (btnB && !isAirborne) {
                // Attack on ground: keep stick magnitude low so Mario punches instead of diving!
                inputs.stickY = movingInEr ? -0.3f : 0.0f;
            } else if (inPunchAction && !isAirborne) {
                // In punch animation: zero out stick so punch combo is not cancelled by movement
                inputs.stickY = 0.0f;
            } else {
                inputs.stickY = movingInEr ? -1.0f : 0.0f;
            }

            inputs.buttonA = btnA;
            inputs.buttonB = btnB;
            inputs.buttonZ = btnZ;

            sm64_mario_tick(marioId, &inputs, &state, &geoBufs);
            TickSM64Audio();

            // pose first, relative to where SM64 really has Mario this tick
            int cnt = sm64_er_get_parts(partMats.data(), triParts.data(), nullptr, nullptr);
            int rightHandTris = 0;
            for (uint16_t t = 0; t < geoBufs.numTrianglesUsed; ++t) {
                if (triParts[t] == RIGHT_HAND_PART) rightHandTris++;
            }
            bool peace = (rightHandTris > FIST_TRIANGLES);
            uint8_t eye = ComputeEyeCell(geoUv.data(), geoBufs.numTrianglesUsed);
            prevPose = currPose;
            currPose = ComputeRelativeParts(partMats.data(), cnt, state.position, eye, peace);

            // Elden Ring owns horizontal movement: keep SM64 X/Z at the origin, only its height is kept
            currSmY = std::max(0.0f, state.position[1]);
            sm64_set_mario_position(marioId, 0.0f, currSmY, 0.0f);

            DealMarioCombatDamage(worldChrManPtr, playerIns, erPos, state);
        }

        float alpha = std::clamp(accum / SM64_DT, 0.0f, 1.0f);
        float smoothSmY = prevSmY + (currSmY - prevSmY) * alpha;

        bool airborne = (state.action & 0x00000800) != 0;
        float extraLiftY = 0.0f;
        if (!airborne) {
            groundErY = erPos.y;
        } else {
            float erRise = std::max(0.0f, erPos.y - groundErY);
            float smRise = std::clamp(smoothSmY * SCALE_ER, 0.0f, 3.8f);
            extraLiftY = std::max(0.0f, smRise - erRise);
        }

        // the model faces where Elden Ring faces the character (same convention as er-mario)
        Quat q = Quat::from_rotation_y(PI_F - erFaceAngle);
        PoseSet blended = BlendPoses(prevPose, currPose, alpha);
        PoseSet charPose = ToCharacterSpace(blended, q, extraLiftY);
        {
            std::lock_guard<std::mutex> lock(g_PoseMutex);
            g_WorldCharPose = charPose;
        }"""

new_loop_chunk = """        Vec3 erPos = {*(float*)(physMod + 0x70), *(float*)(physMod + 0x74), *(float*)(physMod + 0x78)};
        Quat erRot = {*(float*)(physMod + 0x50), *(float*)(physMod + 0x54), *(float*)(physMod + 0x58), *(float*)(physMod + 0x5C)};

        // Wait until the map finishes streaming in (non-zero position)
        if (!worldInitialized && (std::abs(erPos.x) + std::abs(erPos.y) + std::abs(erPos.z) > 1.0f)) {
            origin = erPos;
            lastErPos = erPos;
            sm64_set_mario_position(marioId, 0.0f, 0.0f, 0.0f);
            sm64_set_mario_velocity(marioId, 0.0f, 0.0f, 0.0f);
            sm64_set_mario_health(marioId, 0x0880);
            worldInitialized = true;
            LogMsg("[WORLD] Jogador entrou no mundo em (%.2f, %.2f, %.2f)! Origin fixada.", erPos.x, erPos.y, erPos.z);
        }

        // Detect fast travel / teleports: re-center origin smoothly
        if (worldInitialized) {
            float warpDist = erPos.dist(lastErPos);
            if (warpDist > 8.0f) {
                origin = erPos;
                sm64_set_mario_position(marioId, 0.0f, 0.0f, 0.0f);
                sm64_set_mario_velocity(marioId, 0.0f, 0.0f, 0.0f);
                state.position[0] = 0.0f;
                state.position[1] = 0.0f;
                state.position[2] = 0.0f;
                LogMsg("[WORLD] Teleporte detectado (dist=%.2f m)! Re-centrado.", warpDist);
            }
        }
        lastErPos = erPos;

        // Gather Inputs (Keyboard + Mouse + XInput Controller)
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

        if (hasPad) {
            float lx = xst.Gamepad.sThumbLX / 32768.0f;
            float ly = xst.Gamepad.sThumbLY / 32768.0f;
            float mag = std::sqrt(lx * lx + ly * ly);
            if (mag > 0.2f) {
                stickX = lx;
                stickY = -ly; // SM64: negative Y is forward
            }
            if (xst.Gamepad.wButtons & XINPUT_GAMEPAD_A) rawJump = true;
            if ((xst.Gamepad.wButtons & (XINPUT_GAMEPAD_RIGHT_SHOULDER | XINPUT_GAMEPAD_X)) || (xst.Gamepad.bRightTrigger > 100)) rawAttack = true;
            if (xst.Gamepad.wButtons & XINPUT_GAMEPAD_B) rawDodge = true;
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

        // Latch button presses between 30Hz ticks
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

            bool isAirborne = (state.action & 0x00000800) != 0;
            bool inPunchAction = (state.action == 0x00800380 || state.action == 0x00800457);

            static uint8_t s_LastSentB = 0;
            uint8_t btnB = 0;
            float slen = std::sqrt(stickX * stickX + stickY * stickY);

            if (dodgePressed && slen > 0.2f && !isAirborne) {
                // Dodge while moving = Mario's signature Dive & Rollout!
                btnB = 1;
            } else if (attackPressed) {
                if (inPunchAction && s_LastSentB == 1) {
                    btnB = 0; // pulse for punch combo
                } else {
                    btnB = 1;
                }
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

            bool nowAirborne = (state.action & 0x00000800) != 0;

            if (nowAirborne) {
                // Airborne (Jumping / Long Jump / Dive / Ground Pound):
                // Disable Elden Ring gravity so it does not pull Mario down early!
                *(uint8_t*)(physMod + 0x1d5) = 1; // gravity_disabled = true
                *(float*)(physMod + 0x70) = targetErPos.x;
                *(float*)(physMod + 0x74) = targetErPos.y;
                *(float*)(physMod + 0x78) = targetErPos.z;
                *(uint8_t*)(physMod + 0x91) = 1;  // chr_proxy_pos_update_requested = true
            } else {
                // Grounded: Enable Souls gravity so capsule rests on the terrain
                *(uint8_t*)(physMod + 0x1d5) = 0; // gravity_disabled = false
                *(uint8_t*)(physMod + 0x1d0) = 0; // is_falling = false
                *(uint8_t*)(physMod + 0x1d1) = 1; // is_touching_ground = true
                *(uint8_t*)(physMod + 0x92) = 1;  // standing_on_solid_ground = true
                *(uint8_t*)(physMod + 0x93) = 1;  // touching_solid_ground = true

                *(float*)(physMod + 0x70) = targetErPos.x;
                *(float*)(physMod + 0x78) = targetErPos.z;
                *(uint8_t*)(physMod + 0x91) = 1;  // chr_proxy_pos_update_requested = true

                // Keep origin.y synchronized with actual ground height
                float realGroundY = *(float*)(physMod + 0x74);
                origin.y = realGroundY - state.position[1] * SCALE_ER;
            }

            // Character rotation follows Mario's face angle
            Quat q = Quat::from_rotation_y(PI_F - state.faceAngle);
            *(float*)(physMod + 0x50) = q.x;
            *(float*)(physMod + 0x54) = q.y;
            *(float*)(physMod + 0x58) = q.z;
            *(float*)(physMod + 0x5C) = q.w;

            // Re-centre SM64 coordinate space when traveling beyond 25m
            if (std::abs(state.position[0]) > 2500.0f || std::abs(state.position[2]) > 2500.0f) {
                origin = targetErPos;
                sm64_set_mario_position(marioId, 0.0f, state.position[1], 0.0f);
                state.position[0] = 0.0f;
                state.position[2] = 0.0f;
            }

            DealMarioCombatDamage(worldChrManPtr, playerIns, targetErPos, state);
        }

        float alpha = std::clamp(accum / SM64_DT, 0.0f, 1.0f);
        PoseSet blended = BlendPoses(prevPose, currPose, alpha);
        Quat q = Quat::from_rotation_y(PI_F - state.faceAngle);
        PoseSet charPose = ToCharacterSpace(blended, q, 0.0f);
        {
            std::lock_guard<std::mutex> lock(g_PoseMutex);
            g_WorldCharPose = charPose;
        }"""
assert old_loop_chunk in text, "old_loop_chunk not found"
text = text.replace(old_loop_chunk, new_loop_chunk, 1)

with open(src_path, "w", encoding="utf-8", newline="\r\n") as f:
    f.write(text)

print("[SUCCESS] dll_main.cpp updated successfully!")
