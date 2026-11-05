import os

new_loop_code = """        uintptr_t modBag = *(uintptr_t*)(playerIns + 0x190);
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

        // 1. Read Native Elden Ring Havok Character Transform & Ground State
        Vec3 erPos = {*(float*)(physMod + 0x70), *(float*)(physMod + 0x74), *(float*)(physMod + 0x78)};
        Quat erRot = {*(float*)(physMod + 0x50), *(float*)(physMod + 0x54), *(float*)(physMod + 0x58), *(float*)(physMod + 0x5C)};

        uint8_t rawGround = *(uint8_t*)(physMod + 0x1d1);  // is_touching_ground (Havok contact sensor)
        uint8_t rawFalling = *(uint8_t*)(physMod + 0x1d0); // is_falling
        bool erGrounded = (rawGround != 0);
        bool erAirborne = !erGrounded || (rawFalling != 0);

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
            groundErY = erPos.y;
            lastErPos = erPos;
            sm64_set_mario_position(marioId, 0.0f, 0.0f, 0.0f);
            sm64_set_mario_velocity(marioId, 0.0f, 0.0f, 0.0f);
            sm64_set_mario_health(marioId, 0x0880);
            prevSmY = 0.0f;
            currSmY = 0.0f;
            worldInitialized = true;
            LogMsg("[WORLD] Jogador entrou no mundo em (%.2f, %.2f, %.2f)! Base Havok estavel fixada.", erPos.x, erPos.y, erPos.z);
        }

        // 2. Gather Inputs (Keyboard + Mouse + XInput Gamepad)
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

        // XInput Gamepad (Xbox / DualShock / Generic)
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
            if (justPressed & (XINPUT_GAMEPAD_RIGHT_SHOULDER | XINPUT_GAMEPAD_X)) rawAttack = true;
            if (xst.Gamepad.bRightTrigger > 120) rawAttack = true;
            if (justPressed & XINPUT_GAMEPAD_B) rawDodge = true;

            // Z is held (LT or LB), releases immediately when unpressed
            if ((xst.Gamepad.wButtons & XINPUT_GAMEPAD_LEFT_SHOULDER) || (xst.Gamepad.bLeftTrigger > 120)) {
                rawZ = true;
            }
        }

        // Latch quick button taps between 30Hz ticks
        static bool s_AttackLatched = false;
        static bool s_JumpLatched = false;
        static bool s_DodgeLatched = false;
        if (rawAttack) s_AttackLatched = true;
        if (rawJump) s_JumpLatched = true;
        if (rawDodge) s_DodgeLatched = true;

        float slen = std::clamp(std::sqrt(stickX * stickX + stickY * stickY), 0.0f, 1.0f);

        // Character forward vector in Elden Ring (from er-mario: Quat * (0, 0, -1))
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

        // 3. SM64 Physics Engine 30Hz Simulation Loop
        while (accum >= SM64_DT) {
            accum -= SM64_DT;
            prevSmY = currSmY;

            // Measure real horizontal speed in Elden Ring (m/s)
            Vec3 erDelta = { erPos.x - lastErPos.x, 0.0f, erPos.z - lastErPos.z };
            float horizDist = erDelta.length();
            float horizSpeed = horizDist / SM64_DT; // actual horizontal speed in m/s
            lastErPos = erPos;
            bool movingInEr = (horizDist > 0.005f) || (slen > 0.15f);

            // Sync Mario's facing with the character's facing in Elden Ring
            sm64_set_mario_faceangle(marioId, erFaceAngle);

            bool attackPressed = s_AttackLatched || rawAttack;
            s_AttackLatched = false;
            bool jumpPressed = s_JumpLatched || rawJump;
            s_JumpLatched = false;
            bool dodgePressed = s_DodgeLatched || rawDodge;
            s_DodgeLatched = false;
            bool zPressed = rawZ;

            // A. IMMORTALITY: Keep Mario full health so he NEVER dies from fall damage in SM64
            sm64_set_mario_health(marioId, 0x0880);

            // Action classifications
            bool isSmAirborne = (state.action & 0x00000800) != 0;
            bool inPunchAction = (state.action == 0x00800380 || state.action == 0x00800457);
            bool isCrouchAction = (state.action == 0x0C008220 /* ACT_CROUCHING */ ||
                                   state.action == 0x0C008221 /* ACT_START_CROUCHING */ ||
                                   state.action == 0x04000443 /* ACT_START_CRAWLING */ ||
                                   state.action == 0x04000444 /* ACT_CRAWLING */);

            bool inLandingLag = (state.action == 0x0800023B /* ACT_LONG_JUMP_LAND_STOP */ ||
                                 state.action == 0x0800023A /* ACT_TRIPLE_JUMP_LAND_STOP */ ||
                                 state.action == 0x0800022F /* ACT_BACKFLIP_LAND_STOP */ ||
                                 state.action == 0x08000230 /* ACT_DOUBLE_JUMP_LAND_STOP */ ||
                                 state.action == 0x0C000232 /* ACT_JUMP_LAND_STOP */ ||
                                 state.action == 0x0C00023E /* ACT_BUTT_SLIDE_STOP */ ||
                                 state.action == 0x00000386 /* ACT_STOMACH_SLIDE_STOP */);

            // B. CUTSCENE / DEATH GUARD: Never let dead/cutscene animations lock Mario
            if ((state.action & 0x000001C0) == 0x00000100 /* ACT_GROUP_CUTSCENE: death */ || state.health < 0x100) {
                sm64_set_mario_action(marioId, 0x0C400201 /* ACT_IDLE */);
                sm64_set_mario_health(marioId, 0x0880);
            }

            // C. 100% HAVOK GROUND SYNCHRONIZATION:
            // When Elden Ring's native Havok engine confirms the player is on solid ground:
            if (erGrounded) {
                if (isSmAirborne) {
                    if (state.action == 0x0188088A || state.action == 0x01880888 /* ACT_DIVE */) {
                        sm64_set_mario_action(marioId, 0x00880456 /* ACT_DIVE_SLIDE */);
                    } else if (state.action == 0x008008A9 /* ACT_GROUND_POUND */) {
                        sm64_set_mario_action(marioId, 0x00800236 /* ACT_GROUND_POUND_LAND */);
                    } else {
                        // All normal / double / triple jumps land immediately when touching the floor
                        sm64_set_mario_action(marioId, movingInEr ? 0x04000440 /* ACT_WALKING */ : 0x0C000232 /* ACT_JUMP_LAND_STOP */);
                    }
                }
            } else if (erAirborne) {
                // If player walked or fell off a ledge in Elden Ring:
                if (!isSmAirborne && state.action == 0x04000440 /* ACT_WALKING */) {
                    sm64_set_mario_action(marioId, 0x0100088C /* ACT_FREEFALL */);
                }
            }

            // D. ZERO ANIMATION FREEZES: If moving in ER while in landing lag, immediately resume running!
            if (movingInEr && inLandingLag) {
                sm64_set_mario_action(marioId, 0x04000440 /* ACT_WALKING */);
            }

            // E. CROUCH RELEASE: Releasing Z instantly stands Mario up
            if (!zPressed && isCrouchAction) {
                sm64_set_mario_action(marioId, movingInEr ? 0x04000440 /* ACT_WALKING */ : 0x0C400201 /* ACT_IDLE */);
            }

            // F. DIVE SLIDE ROLLOUT & RECOVERY:
            static int s_DiveSlideTicks = 0;
            if (state.action == 0x00880456 /* ACT_DIVE_SLIDE */ || state.action == 0x00000386 /* ACT_STOMACH_SLIDE_STOP */) {
                // Rollout on jump press:
                if (jumpPressed) {
                    sm64_set_mario_action(marioId, 0x010008A6 /* ACT_FORWARD_ROLLOUT */);
                    jumpPressed = false;
                    s_DiveSlideTicks = 0;
                } else if (movingInEr) {
                    s_DiveSlideTicks++;
                    // Slide for 5 frames (~160ms) then smoothly transition to running:
                    if (s_DiveSlideTicks > 5) {
                        sm64_set_mario_action(marioId, 0x04000440 /* ACT_WALKING */);
                        s_DiveSlideTicks = 0;
                    }
                } else {
                    s_DiveSlideTicks = 0;
                }
            } else {
                s_DiveSlideTicks = 0;
            }

            // G. SKID / 180° BRAKE: Classic SM64 screech turn when sharply reversing direction while running
            static Vec3 s_PrevMoveDir = {0.0f, 0.0f, 1.0f};
            if (movingInEr && horizDist > 0.02f) {
                Vec3 curMoveDir = erDelta * (1.0f / horizDist);
                float dirDot = curMoveDir.x * s_PrevMoveDir.x + curMoveDir.z * s_PrevMoveDir.z;
                if (dirDot < -0.4f && erGrounded && horizSpeed > 2.8f && !isSmAirborne && !inPunchAction) {
                    sm64_set_mario_action(marioId, 0x04000445 /* ACT_BRAKING */);
                }
                s_PrevMoveDir = curMoveDir;
            }

            // H. ANTI-FREEZE WATCHDOG: If Mario is locked in ANY non-walking action for > 20 ticks (~0.6s) while moving, stand up!
            static uint32_t s_LastAction = 0;
            static int s_SameActionTicks = 0;
            if (state.action == s_LastAction) {
                s_SameActionTicks++;
            } else {
                s_LastAction = state.action;
                s_SameActionTicks = 0;
            }
            if (movingInEr && s_SameActionTicks > 20 && state.action != 0x04000440 /* ACT_WALKING */ && state.action != 0x0C400201 /* ACT_IDLE */) {
                sm64_set_mario_action(marioId, 0x04000440 /* ACT_WALKING */);
                s_SameActionTicks = 0;
            }

            // I. BUTTON SIGNALS
            static uint8_t s_LastSentB = 0;
            uint8_t btnB = 0;
            if (dodgePressed && movingInEr && !isSmAirborne) {
                // Dodge while moving = Dive!
                btnB = 1;
            } else if (attackPressed) {
                // 3-hit punch combo: pulse B button
                btnB = (inPunchAction && s_LastSentB == 1) ? 0 : 1;
            }
            s_LastSentB = btnB;

            uint8_t btnA = jumpPressed ? 1 : 0;
            uint8_t btnZ = zPressed ? 1 : 0;

            inputs.camLookX = -dir.x;
            inputs.camLookZ = dir.z;

            // J. DYNAMIC ANALOG SPEED CURVE (Ponta dos pés -> Trote -> Corrida -> Sprint):
            float dynamicStickY = 0.0f;
            if (movingInEr) {
                if (horizSpeed < 1.4f) {
                    dynamicStickY = -0.32f; // Tiptoe / caminhada lenta
                } else if (horizSpeed < 3.5f) {
                    dynamicStickY = -0.65f; // Caminhada / trote médio
                } else if (horizSpeed < 6.0f) {
                    dynamicStickY = -0.90f; // Corrida padrão
                } else {
                    dynamicStickY = -1.0f;  // Sprint total
                }
            }

            if (state.action == 0x04000445 /* ACT_BRAKING: skid */) {
                inputs.stickX = 0.0f;
                inputs.stickY = 0.0f;
            } else if (inPunchAction && !isSmAirborne) {
                inputs.stickX = 0.0f;
                inputs.stickY = 0.0f;
            } else if (dodgePressed && movingInEr && !isSmAirborne) {
                inputs.stickX = 0.0f;
                inputs.stickY = -1.0f; // Dive needs full stick
            } else if (btnB && !isSmAirborne) {
                inputs.stickX = 0.0f;
                inputs.stickY = movingInEr ? -0.3f : 0.0f;
            } else if (movingInEr) {
                inputs.stickX = 0.0f;
                inputs.stickY = dynamicStickY;
            } else {
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
            prevPose = currPose;
            currPose = ComputeRelativeParts(partMats.data(), cnt, state.position, eye, peace);

            // Keep SM64 X/Z at origin, height is tracked for acrobatic jumps
            currSmY = std::max(0.0f, state.position[1]);
            sm64_set_mario_position(marioId, 0.0f, currSmY, 0.0f);
            state.position[0] = 0.0f;
            state.position[2] = 0.0f;

            // Combat damage against enemies and bosses
            DealMarioCombatDamage(worldChrManPtr, playerIns, erPos, state);
        }

        // Keep stamina full so player can jump and attack infinitely with Mario
        int32_t maxSp = *(int32_t*)(dataMod + 0x158);
        if (maxSp > 0) *(int32_t*)(dataMod + 0x154) = maxSp;

        float alpha = std::clamp(accum / SM64_DT, 0.0f, 1.0f);
        float smoothSmY = prevSmY + (currSmY - prevSmY) * alpha;

        // 4. VISUAL ACROBATIC LIFT: Only applied when character is genuinely airborne in Elden Ring!
        float extraLiftY = 0.0f;
        if (erAirborne) {
            float smRise = std::max(0.0f, smoothSmY * SCALE_ER);
            float erRise = std::max(0.0f, erPos.y - groundErY);
            extraLiftY = std::clamp(smRise - erRise, 0.0f, 1.8f);
        } else {
            // Strictly 0.0f on solid ground so Mario NEVER walks on air or floats above the floor!
            extraLiftY = 0.0f;
            groundErY = erPos.y; // calibrate ground base height
        }

        // Model faces where Elden Ring faces the character
        Quat q = Quat::from_rotation_y(PI_F - erFaceAngle);
        PoseSet blended = BlendPoses(prevPose, currPose, alpha);
        PoseSet charPose = ToCharacterSpace(blended, q, extraLiftY);
        {
            std::lock_guard<std::mutex> lock(g_PoseMutex);
            g_WorldCharPose = charPose;
        }

        Sleep(1);
    }
    return 0;
}
"""

file_path = r"D:\Modding\MarioPhysics\src\dll_main.cpp"
with open(file_path, "r", encoding="utf-8") as f:
    text = f.read()

# Collapse double newlines
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

marker_start = "uintptr_t modBag = *(uintptr_t*)(playerIns + 0x190);"
marker_end = "BOOL APIENTRY DllMain"

pos1 = content.find(marker_start)
pos2 = content.find(marker_end)
assert pos1 != -1 and pos2 != -1, f"pos1: {pos1}, pos2: {pos2}"

updated = content[:pos1] + new_loop_code + "\n\n" + content[pos2:]

# Convert to standard Windows CRLF
final_text = updated.replace("\r\n", "\n").replace("\n", "\r\n")

with open(file_path, "w", encoding="utf-8") as f:
    f.write(final_text)

print("Updated dll_main.cpp successfully.")

