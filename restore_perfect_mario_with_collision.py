import os

file_path = r"D:\Modding\MarioPhysics\src\dll_main.cpp"

with open(file_path, "r", encoding="utf-8") as f:
    text = f.read()

# 1. Update Detour_XInputGetState so left stick is zeroed for Elden Ring
old_detour = """static DWORD WINAPI Detour_XInputGetState(DWORD dwUserIndex, XINPUT_STATE* pState) {
    if (!Original_XInputGetState) return ERROR_DEVICE_NOT_CONNECTED;
    DWORD res = Original_XInputGetState(dwUserIndex, pState);
    if (res == ERROR_SUCCESS && pState && dwUserIndex == 0) {
        g_RawPad = *pState;
        g_PadCaptured = true;
        // Native Elden Ring Havok handles character movement with the left stick smoothly
    }
    return res;
}"""

new_detour = """static DWORD WINAPI Detour_XInputGetState(DWORD dwUserIndex, XINPUT_STATE* pState) {
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
}"""

# 2. Add CastRayER before GetCameraForward if not present
cast_ray_definition = """// --- Havok Raycasting for Wall and Ground Environment Collision ---
struct HavokPosition {
    float x = 0.0f;
    float y = 0.0f;
    float z = 0.0f;
    float w = 0.0f;
};

static bool CastRayER(uintptr_t exeBase, uintptr_t playerIns, const Vec3& from, const Vec3& delta, Vec3& hitPos, uint32_t filter = 0x08) {
    if (!exeBase) return false;

    // CSHavokMan singleton at exeBase + 0x3d76068
    uintptr_t havokManPtr = *(uintptr_t*)(exeBase + 0x3d76068);
    if (!havokManPtr) {
        typedef void* (*FnGetHavokMan)();
        FnGetHavokMan getHavokMan = (FnGetHavokMan)(exeBase + 0xc4ff50);
        havokManPtr = (uintptr_t)getHavokMan();
    }
    if (!IsValidPtr(havokManPtr, 0xa0)) return false;

    void* physWorld = *(void**)(havokManPtr + 0x98);
    if (!physWorld || !IsValidPtr((uintptr_t)physWorld, 0x10)) return false;

    HavokPosition start = {from.x, from.y, from.z, 0.0f};
    HavokPosition ext   = {delta.x, delta.y, delta.z, 0.0f};
    HavokPosition outHit = {};

    typedef bool (*FnCastRay)(void* physWorld, uint32_t filter, const HavokPosition* start, const HavokPosition* delta, HavokPosition* outHit, void* owner);
    FnCastRay castRay = (FnCastRay)(exeBase + 0xc722c0); // Verified RVA for Elden Ring

    bool hit = castRay(physWorld, filter, &start, &ext, &outHit, (void*)playerIns);
    if (hit) {
        hitPos = {outHit.x, outHit.y, outHit.z};
        return true;
    }
    return false;
}

"""

# 3. The complete MainLoopThread body for the "Tava Perfeito" version with wall collision
perfect_loop_code = """    uintptr_t worldChrManPtr = FindWorldChrMan(exeBase, exeSize);
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
        bool inWorldCoords = (std::abs(erPos.x) < 50000.0f && std::abs(erPos.z) < 50000.0f && 
                              std::abs(erPos.y) < 5000.0f &&
                              (std::abs(erPos.x) > 5.0f || std::abs(erPos.z) > 5.0f || erPos.y > 10.0f));
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

            // --- 1. ENVIRONMENT WALL COLLISION & SLIDE SWEEP ---
            constexpr float PLAYER_RADIUS = 0.35f;
            Vec3 moveDelta = targetErPos - currentErPos;
            float horizMove = std::sqrt(moveDelta.x * moveDelta.x + moveDelta.z * moveDelta.z);

            Vec3 finalTarget = targetErPos;
            bool hitWallX = false;
            bool hitWallZ = false;

            if (horizMove > 0.0005f) {
                // Test at knee (0.4m) and chest (1.1m)
                float rayHeights[2] = {currentErPos.y + 0.40f, currentErPos.y + 1.10f};

                // Test X axis movement
                if (std::abs(moveDelta.x) > 0.0002f) {
                    float signX = (moveDelta.x > 0.0f) ? 1.0f : -1.0f;
                    float probeDistX = std::abs(moveDelta.x) + PLAYER_RADIUS;
                    Vec3 rayDeltaX = {signX * probeDistX, 0.0f, 0.0f};

                    for (float h : rayHeights) {
                        Vec3 hitPoint;
                        Vec3 rayStart = {currentErPos.x, h, currentErPos.z};
                        if (CastRayER(exeBase, playerIns, rayStart, rayDeltaX, hitPoint, 0x08)) {
                            float distToHit = std::abs(hitPoint.x - currentErPos.x);
                            if (distToHit <= probeDistX) {
                                hitWallX = true;
                                float allowedX = std::max(0.0f, distToHit - PLAYER_RADIUS);
                                finalTarget.x = currentErPos.x + signX * allowedX;
                                break;
                            }
                        }
                    }
                }

                // Test Z axis movement
                if (std::abs(moveDelta.z) > 0.0002f) {
                    float signZ = (moveDelta.z > 0.0f) ? 1.0f : -1.0f;
                    float probeDistZ = std::abs(moveDelta.z) + PLAYER_RADIUS;
                    Vec3 rayDeltaZ = {0.0f, 0.0f, signZ * probeDistZ};

                    for (float h : rayHeights) {
                        Vec3 hitPoint;
                        Vec3 rayStart = {finalTarget.x, h, currentErPos.z};
                        if (CastRayER(exeBase, playerIns, rayStart, rayDeltaZ, hitPoint, 0x08)) {
                            float distToHit = std::abs(hitPoint.z - currentErPos.z);
                            if (distToHit <= probeDistZ) {
                                hitWallZ = true;
                                float allowedZ = std::max(0.0f, distToHit - PLAYER_RADIUS);
                                finalTarget.z = currentErPos.z + signZ * allowedZ;
                                break;
                            }
                        }
                    }
                }

                if (hitWallX || hitWallZ) {
                    targetErPos.x = finalTarget.x;
                    targetErPos.z = finalTarget.z;

                    // Sync clamped coordinates back to libsm64 so Mario slides along walls
                    float sm64_x = -(targetErPos.x - origin.x) / SCALE_ER;
                    float sm64_z =  (targetErPos.z - origin.z) / SCALE_ER;
                    sm64_set_mario_position(marioId, sm64_x, state.position[1], sm64_z);
                    state.position[0] = sm64_x;
                    state.position[2] = sm64_z;

                    if (hitWallX && hitWallZ) {
                        sm64_set_mario_velocity(marioId, 0.0f, state.velocity[1], 0.0f);
                    }
                }
            }

            // --- 2. ENVIRONMENT GROUND & ABYSS DETECTION ---
            bool nowAirborne = (state.action & 0x00000800) != 0;

            // Probe ground directly under Mario
            Vec3 groundStart = {targetErPos.x, currentErPos.y + 0.60f, targetErPos.z};
            Vec3 groundDelta = {0.0f, -5.0f, 0.0f};
            Vec3 groundHit;
            bool groundFound = CastRayER(exeBase, playerIns, groundStart, groundDelta, groundHit, 0x08);

            if (groundFound) {
                lastSafeGroundY = groundHit.y;
            }

            if (nowAirborne) {
                // Airborne (Jumping / Long Jump / Dive / Ground Pound):
                *(uint8_t*)(physMod + 0x1d5) = 1; // gravity_disabled = true

                // Check landing: if Mario has descended to or below the terrain surface
                if (groundFound && targetErPos.y <= groundHit.y + 0.05f) {
                    targetErPos.y = groundHit.y;
                    origin.y = groundHit.y - state.position[1] * SCALE_ER;
                }

                *(float*)(physMod + 0x70) = targetErPos.x;
                *(float*)(physMod + 0x74) = targetErPos.y;
                *(float*)(physMod + 0x78) = targetErPos.z;
                *(uint8_t*)(physMod + 0x91) = 1;  // chr_proxy_pos_update_requested = true
            } else {
                // Grounded:
                if (groundFound) {
                    float dy = groundHit.y - currentErPos.y;
                    if (dy < 1.0f) { // Smooth step up / down stairs and ramps
                        targetErPos.y = groundHit.y;
                        origin.y = groundHit.y - state.position[1] * SCALE_ER;
                    }
                } else {
                    // Stepping over cliff or void: lock origin to last safe ground
                    targetErPos.y = lastSafeGroundY + state.position[1] * SCALE_ER;
                    origin.y = lastSafeGroundY - state.position[1] * SCALE_ER;
                }

                *(uint8_t*)(physMod + 0x1d5) = 0; // gravity_disabled = false
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
"""

# Let's perform the clean replacement
clean_lines = []
last_empty = False
for line in text.splitlines():
    l = line.rstrip()
    if not l:
        if not last_empty:
            clean_lines.append("")
            last_empty = True
    else:
        clean_lines.append(l)
        last_empty = False

content = "\n".join(clean_lines)

# 1. Update Detour_XInputGetState
if old_detour in content:
    content = content.replace(old_detour, new_detour)
    print("Detour_XInputGetState updated.")

# 2. Add CastRayER before GetCameraForward if not present
if "CastRayER" not in content:
    cam_marker = "// --- Camera Forward Scanner"
    pos_cam = content.find(cam_marker)
    assert pos_cam != -1, "Camera forward scanner marker not found"
    content = content[:pos_cam] + cast_ray_definition + content[pos_cam:]
    print("CastRayER added.")

# 3. Replace MainLoopThread loop
start_marker = "    uintptr_t worldChrManPtr = FindWorldChrMan(exeBase, exeSize);"
end_marker = "BOOL APIENTRY DllMain"

pos_start = content.find(start_marker)
pos_end = content.find(end_marker)
assert pos_start != -1 and pos_end != -1, f"start: {pos_start}, end: {pos_end}"

final_content = content[:pos_start] + perfect_loop_code + "\n\n" + content[pos_end:]

# Convert to standard Windows CRLF
final_text = final_content.replace("\r\n", "\n").replace("\n", "\r\n")

with open(file_path, "w", encoding="utf-8") as f:
    f.write(final_text)

print("[SUCCESS] dll_main.cpp rolled back to the perfect version + wall collision fix!")

