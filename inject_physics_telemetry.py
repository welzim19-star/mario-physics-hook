import sys

with open(r'D:\Modding\MarioPhysics\src\dll_main.cpp', 'r', encoding='utf-8') as f:
    text = f.read()

end_marker = 'DealMarioCombatDamage(worldChrManPtr, playerIns, targetErPos, state);'
start_marker = 'sm64_mario_tick(marioId, &inputs, &state, &geoBufs);\n            TickSM64Audio();'

start_idx = text.rfind(start_marker, 0, text.rfind(end_marker))
if start_idx == -1:
    # Try CRLF
    start_marker = start_marker.replace('\n', '\r\n')
    start_idx = text.rfind(start_marker, 0, text.rfind(end_marker))

if start_idx == -1:
    print("Could not find start marker!")
    sys.exit(1)

end_idx = text.find(end_marker, start_idx)
if end_idx == -1:
    print("Could not find end marker!")
    sys.exit(1)

new_block = '''sm64_mario_tick(marioId, &inputs, &state, &geoBufs);
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
                g_pTelemetryShm->actionName[sizeof(g_pTelemetryShm->actionName) - 1] = '\\0';
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
            '''

# Replace slice
text = text[:start_idx] + new_block + text[end_idx:]

with open(r'D:\Modding\MarioPhysics\src\dll_main.cpp', 'w', encoding='utf-8') as f:
    f.write(text)

print("Injected physics telemetry block successfully!")

