"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import * as THREE from "three";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";
import {
  STATUS_COLOR,
  daysUntil,
  formatDate,
  initialKuehe,
  ohrmarkeFor,
  type Kuh,
  type KuhStatus,
} from "@/lib/herd";

const PLATE_H = 1.7; // Zielhoehe der Foto-Aufsteller in 3D-Einheiten
type Mode = "orbit" | "walk";

export default function Stall3DPage() {
  const kuehe = initialKuehe;
  const mountRef = useRef<HTMLDivElement>(null);
  const [selected, setSelected] = useState<Kuh | null>(null);
  const [hover, setHover] = useState<{ kuh: Kuh; x: number; y: number } | null>(
    null,
  );
  const [mode, setMode] = useState<Mode>("orbit");

  const resetViewRef = useRef<(() => void) | null>(null);
  const modeRef = useRef<Mode>("orbit");
  const moveRef = useRef({ f: 0, s: 0 }); // forward/-back, strafe
  const setModeRef = useRef<((m: Mode) => void) | null>(null);

  // Steuert die On-Screen-Bewegung (D-Pad / Joystick) und Tastatur gemeinsam.
  const press = (f: number, s: number) => {
    moveRef.current = { f, s };
  };
  const release = () => {
    moveRef.current = { f: 0, s: 0 };
  };

  useEffect(() => {
    const mount = mountRef.current;
    if (!mount) return;

    let disposed = false;
    let cleanup: (() => void) | undefined;

    (() => {
      if (disposed || !mount) return;

      const herd = kuehe;
      const numCows = herd.length;
      const spacing = 2.2;
      const startX = -((numCows - 1) * spacing) / 2;

      const width = mount.clientWidth;
      const height = mount.clientHeight;

      const scene = new THREE.Scene();
      scene.background = new THREE.Color("#cdbfa6");
      scene.fog = new THREE.Fog("#cdbfa6", 40, 95);

      const camera = new THREE.PerspectiveCamera(62, width / height, 0.3, 160);
      const defaultCamPos = new THREE.Vector3(startX - 2.5, 1.65, -2.5);
      const target = new THREE.Vector3(startX + 16, 1.45, -0.5);
      camera.position.copy(defaultCamPos);
      camera.lookAt(target);

      const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
      renderer.setSize(width, height);
      renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
      renderer.shadowMap.enabled = true;
      renderer.shadowMap.type = THREE.PCFSoftShadowMap;
      renderer.toneMapping = THREE.ACESFilmicToneMapping;
      renderer.toneMappingExposure = 1.1;
      mount.appendChild(renderer.domElement);
      renderer.domElement.style.display = "block";
      renderer.domElement.style.cursor = "grab";
      renderer.domElement.style.touchAction = "none";

      // --- Licht ---
      scene.add(new THREE.AmbientLight("#ffe8c8", 1.2));
      const sun = new THREE.DirectionalLight("#fffef5", 2.4);
      sun.position.set(25, 30, 10);
      sun.castShadow = true;
      sun.shadow.mapSize.set(2048, 2048);
      sun.shadow.camera.near = 0.5;
      sun.shadow.camera.far = 160;
      sun.shadow.camera.left = -70;
      sun.shadow.camera.right = 70;
      sun.shadow.camera.top = 30;
      sun.shadow.camera.bottom = -10;
      sun.shadow.bias = -0.0004;
      sun.shadow.normalBias = 0.02;
      scene.add(sun);
      const fill = new THREE.DirectionalLight("#d4e0ff", 0.9);
      fill.position.set(-10, 8, -5);
      scene.add(fill);

      const geometries: THREE.BufferGeometry[] = [];
      const materials: THREE.Material[] = [];
      const textures: THREE.Texture[] = [];
      const track = <T extends THREE.BufferGeometry | THREE.Material>(
        o: T,
      ): T => {
        if ((o as THREE.BufferGeometry).isBufferGeometry)
          geometries.push(o as THREE.BufferGeometry);
        else materials.push(o as THREE.Material);
        return o;
      };

      // --- Boden ---
      const floorW = Math.max(85, numCows * spacing + 12);
      const floor = new THREE.Mesh(
        track(new THREE.PlaneGeometry(floorW, 28)),
        track(
          new THREE.MeshStandardMaterial({
            color: "#c8c0b2",
            roughness: 0.75,
            metalness: 0.05,
          }),
        ),
      );
      floor.rotation.x = -Math.PI / 2;
      floor.position.y = -0.02;
      floor.receiveShadow = true;
      scene.add(floor);

      const stripeGeo = track(new THREE.PlaneGeometry(floorW, 0.25));
      const stripeMat = track(
        new THREE.MeshStandardMaterial({ color: "#b0a898", roughness: 0.8 }),
      );
      for (let i = -3; i <= 4; i++) {
        const stripe = new THREE.Mesh(stripeGeo, stripeMat);
        stripe.rotation.x = -Math.PI / 2;
        stripe.position.set(0, -0.01, i * 2.8);
        stripe.receiveShadow = true;
        scene.add(stripe);
      }

      // --- Futtertisch ---
      const tableLength = numCows * spacing + 2;
      const tableHeight = 0.65;
      const table = new THREE.Mesh(
        track(new THREE.BoxGeometry(tableLength, tableHeight, 1.5)),
        track(
          new THREE.MeshStandardMaterial({
            color: "#d5d3cf",
            roughness: 0.45,
            metalness: 0.15,
          }),
        ),
      );
      table.position.set(0, tableHeight / 2, 0.85);
      table.castShadow = true;
      table.receiveShadow = true;
      scene.add(table);
      const tableTop = new THREE.Mesh(
        track(new THREE.BoxGeometry(tableLength - 0.1, 0.08, 1.4)),
        track(
          new THREE.MeshStandardMaterial({
            color: "#e0ded9",
            roughness: 0.35,
            metalness: 0.2,
          }),
        ),
      );
      tableTop.position.set(0, tableHeight + 0.02, 0.85);
      tableTop.receiveShadow = true;
      scene.add(tableTop);

      // --- Fressgitter ---
      const postGeo = track(new THREE.CylinderGeometry(0.04, 0.05, 1.1, 8));
      const postMat = track(
        new THREE.MeshStandardMaterial({
          color: "#7a7a7a",
          roughness: 0.3,
          metalness: 0.85,
        }),
      );
      const postTopGeo = track(new THREE.CylinderGeometry(0.06, 0.04, 0.15, 8));
      const barGeo = track(new THREE.BoxGeometry(1.9, 0.06, 0.06));
      const barMat = track(
        new THREE.MeshStandardMaterial({
          color: "#888888",
          roughness: 0.35,
          metalness: 0.8,
        }),
      );
      const gateZ = 1.52;

      for (let i = 0; i < numCows; i++) {
        const x = startX + i * spacing;
        for (let side = -1; side <= 1; side += 2) {
          const px = x + side * 0.8;
          const post = new THREE.Mesh(postGeo, postMat);
          post.position.set(px, tableHeight + 0.45, gateZ);
          post.castShadow = true;
          scene.add(post);
          const postTop = new THREE.Mesh(postTopGeo, postMat);
          postTop.position.set(px, tableHeight + 0.98, gateZ);
          scene.add(postTop);
        }
        const bar = new THREE.Mesh(barGeo, barMat);
        bar.position.set(x, tableHeight + 0.88, gateZ);
        scene.add(bar);
        const bar2 = new THREE.Mesh(barGeo, barMat);
        bar2.position.set(x, tableHeight + 0.52, gateZ);
        scene.add(bar2);
      }

      // --- Stallgebaeude: Waende, Decke, Binder, Lampen ---
      const barnW = floorW + 2;
      const barnD = 28;
      const wallH = 4.8;
      const wallMat = track(
        new THREE.MeshStandardMaterial({
          color: "#bfb49e",
          roughness: 0.88,
          metalness: 0.0,
          side: THREE.FrontSide,
        }),
      );

      const wallBackGeo = track(new THREE.BoxGeometry(barnW, wallH, 0.25));
      const wBack = new THREE.Mesh(wallBackGeo, wallMat);
      wBack.position.set(0, wallH / 2, -barnD / 2);
      wBack.receiveShadow = true;
      scene.add(wBack);
      const wFront = new THREE.Mesh(wallBackGeo, wallMat);
      wFront.position.set(0, wallH / 2, barnD / 2);
      wFront.receiveShadow = true;
      scene.add(wFront);
      const wallSideGeo = track(new THREE.BoxGeometry(0.25, wallH, barnD));
      const wLeft = new THREE.Mesh(wallSideGeo, wallMat);
      wLeft.position.set(-barnW / 2, wallH / 2, 0);
      wLeft.receiveShadow = true;
      scene.add(wLeft);
      const wRight = new THREE.Mesh(wallSideGeo, wallMat);
      wRight.position.set(barnW / 2, wallH / 2, 0);
      wRight.receiveShadow = true;
      scene.add(wRight);

      const ceilMat = track(
        new THREE.MeshStandardMaterial({
          color: "#d8cfc0",
          roughness: 0.92,
          side: THREE.BackSide,
        }),
      );
      const ceil = new THREE.Mesh(
        track(new THREE.PlaneGeometry(barnW, barnD)),
        ceilMat,
      );
      ceil.rotation.x = Math.PI / 2;
      ceil.position.set(0, wallH, 0);
      scene.add(ceil);

      const binderMat = track(
        new THREE.MeshStandardMaterial({ color: "#7a5c3a", roughness: 0.82 }),
      );
      const binderGeo = track(new THREE.BoxGeometry(barnW, 0.18, 0.28));
      for (let bz = -10; bz <= 12; bz += 5.5) {
        const binder = new THREE.Mesh(binderGeo, binderMat);
        binder.position.set(0, wallH - 0.09, bz);
        binder.castShadow = true;
        scene.add(binder);
      }

      const lampBodyGeo = track(new THREE.CylinderGeometry(0.22, 0.26, 0.18, 10));
      const lampBodyMat = track(
        new THREE.MeshStandardMaterial({ color: "#e8e0d0", roughness: 0.5 }),
      );
      const lampGlowMat = track(
        new THREE.MeshStandardMaterial({
          color: "#fffbe0",
          emissive: "#fffbe0",
          emissiveIntensity: 1.2,
          roughness: 1,
        }),
      );
      const lampGlowGeo = track(new THREE.CircleGeometry(0.2, 10));
      for (let bz = -10; bz <= 12; bz += 5.5) {
        const lb = new THREE.Mesh(lampBodyGeo, lampBodyMat);
        lb.position.set(0, wallH - 0.28, bz);
        scene.add(lb);
        const lg = new THREE.Mesh(lampGlowGeo, lampGlowMat);
        lg.rotation.x = Math.PI / 2;
        lg.position.set(0, wallH - 0.37, bz);
        scene.add(lg);
        const pl = new THREE.PointLight("#fff5d8", 2.2, 22, 1.6);
        pl.position.set(0, wallH - 0.5, bz);
        scene.add(pl);
      }

      // --- Platzhalter-Textur (per Canvas) ---
      function buildDefaultTexture(nr: number, name: string): THREE.CanvasTexture {
        const W = 512;
        const H = 640;
        const canvas = document.createElement("canvas");
        canvas.width = W;
        canvas.height = H;
        const ctx = canvas.getContext("2d")!;
        ctx.clearRect(0, 0, W, H);
        ctx.fillStyle = "#f5f0e8";
        ctx.beginPath();
        ctx.ellipse(W / 2, H / 2 + 20, 170, 220, 0, 0, Math.PI * 2);
        ctx.fill();
        ctx.fillStyle = "#d8b4a0";
        ctx.beginPath();
        ctx.ellipse(W / 2, H / 2 + 190, 100, 70, 0, 0, Math.PI * 2);
        ctx.fill();
        ctx.fillStyle = "#5a3a28";
        ctx.beginPath();
        ctx.ellipse(W / 2 - 35, H / 2 + 200, 12, 18, 0, 0, Math.PI * 2);
        ctx.ellipse(W / 2 + 35, H / 2 + 200, 12, 18, 0, 0, Math.PI * 2);
        ctx.fill();
        ctx.fillStyle = "#2a1f15";
        ctx.beginPath();
        ctx.ellipse(W / 2 - 60, H / 2 + 20, 14, 18, 0, 0, Math.PI * 2);
        ctx.ellipse(W / 2 + 60, H / 2 + 20, 14, 18, 0, 0, Math.PI * 2);
        ctx.fill();
        ctx.fillStyle = "#e8e0d5";
        ctx.beginPath();
        ctx.ellipse(W / 2 - 165, H / 2 - 100, 55, 80, -0.5, 0, Math.PI * 2);
        ctx.ellipse(W / 2 + 165, H / 2 - 100, 55, 80, 0.5, 0, Math.PI * 2);
        ctx.fill();
        ctx.strokeStyle = "#e8e0d0";
        ctx.lineWidth = 22;
        ctx.lineCap = "round";
        ctx.beginPath();
        ctx.moveTo(W / 2 - 110, H / 2 - 150);
        ctx.quadraticCurveTo(W / 2 - 205, H / 2 - 250, W / 2 - 235, H / 2 - 190);
        ctx.moveTo(W / 2 + 110, H / 2 - 150);
        ctx.quadraticCurveTo(W / 2 + 205, H / 2 - 250, W / 2 + 235, H / 2 - 190);
        ctx.stroke();
        ctx.fillStyle = "#e8c75e";
        ctx.fillRect(W / 2 + 88, H / 2 + 110, 80, 50);
        ctx.fillStyle = "#2a1f15";
        ctx.font = "bold 28px sans-serif";
        ctx.textAlign = "center";
        ctx.fillText(String(nr), W / 2 + 128, H / 2 + 145);
        ctx.font = "bold 34px sans-serif";
        ctx.fillStyle = "#3a3025";
        ctx.fillText(name, W / 2, H - 20);
        const tex = new THREE.CanvasTexture(canvas);
        tex.colorSpace = THREE.SRGBColorSpace;
        tex.anisotropy = 4;
        textures.push(tex);
        return tex;
      }

      type CowEntry = {
        group: THREE.Group;
        plate: THREE.Mesh;
        plateMat: THREE.MeshStandardMaterial;
        marker: THREE.Mesh;
        markerBaseY: number;
        kuh: Kuh;
      };
      const cows: CowEntry[] = [];

      function applyAspect(entry: CowEntry, aspect: number) {
        const w = PLATE_H * aspect;
        entry.plate.scale.set(w, PLATE_H, 1);
      }

      function buildCow(kuh: Kuh): CowEntry {
        const group = new THREE.Group();
        group.userData = { nr: kuh.nr };

        const plateGeo = track(new THREE.PlaneGeometry(1, 1));
        const fallback = buildDefaultTexture(kuh.nr, kuh.name);
        const plateMat = track(
          new THREE.MeshStandardMaterial({
            map: fallback,
            transparent: true,
            alphaTest: 0.04,
            side: THREE.DoubleSide,
            roughness: 0.85,
            metalness: 0,
          }),
        );
        const plate = new THREE.Mesh(plateGeo, plateMat);
        plate.position.set(0, PLATE_H / 2 + 0.02, gateZ + 0.05);
        plate.castShadow = true;
        plate.scale.set(PLATE_H * 0.8, PLATE_H, 1);
        group.add(plate);

        const shadow = new THREE.Mesh(
          track(new THREE.CircleGeometry(0.55, 24)),
          track(
            new THREE.MeshBasicMaterial({
              color: "#000000",
              transparent: true,
              opacity: 0.16,
            }),
          ),
        );
        shadow.rotation.x = -Math.PI / 2;
        shadow.position.set(0, 0.015, gateZ + 0.05);
        shadow.scale.set(1, 0.6, 1);
        group.add(shadow);

        const markerColor = STATUS_COLOR[kuh.status];
        const markerBaseY = PLATE_H + 0.32;
        const marker = new THREE.Mesh(
          track(new THREE.SphereGeometry(0.15, 16, 16)),
          track(
            new THREE.MeshStandardMaterial({
              color: markerColor,
              emissive: markerColor,
              emissiveIntensity: 0.6,
              roughness: 0.35,
            }),
          ),
        );
        marker.position.set(0, markerBaseY, gateZ + 0.05);
        group.add(marker);
        const stalk = new THREE.Mesh(
          track(new THREE.CylinderGeometry(0.014, 0.014, 0.28, 6)),
          track(new THREE.MeshStandardMaterial({ color: "#999", roughness: 0.6 })),
        );
        stalk.position.set(0, PLATE_H + 0.14, gateZ + 0.05);
        group.add(stalk);

        const entry: CowEntry = {
          group,
          plate,
          plateMat,
          marker,
          markerBaseY,
          kuh,
        };
        applyAspect(entry, 512 / 640);
        return entry;
      }

      herd.forEach((kuh, i) => {
        const entry = buildCow(kuh);
        entry.group.position.set(startX + i * spacing, 0, -1.55);
        scene.add(entry.group);
        cows.push(entry);
      });

      // --- Orbit-Controls ---
      const controls = new OrbitControls(camera, renderer.domElement);
      controls.target.copy(target);
      controls.enableDamping = true;
      controls.dampingFactor = 0.12;
      controls.minDistance = 0.8;
      controls.maxDistance = 55;
      controls.maxPolarAngle = Math.PI / 1.85;
      controls.minPolarAngle = 0.08;
      controls.panSpeed = 1.4;
      controls.zoomSpeed = 1.2;
      controls.update();

      resetViewRef.current = () => {
        camera.position.copy(defaultCamPos);
        controls.target.copy(target);
        controls.update();
      };

      // --- First-Person ("Begehen") ---
      const euler = new THREE.Euler(0, 0, 0, "YXZ");
      const EYE = 1.6;
      const halfW = floorW / 2 - 1.5;
      const setWalkFromCamera = () => {
        euler.setFromQuaternion(camera.quaternion);
      };
      const applyMode = (m: Mode) => {
        modeRef.current = m;
        controls.enabled = m === "orbit";
        if (m === "walk") {
          camera.position.set(
            THREE.MathUtils.clamp(camera.position.x, -halfW, halfW),
            EYE,
            -2.5,
          );
          setWalkFromCamera();
          renderer.domElement.style.cursor = "crosshair";
        } else {
          renderer.domElement.style.cursor = "grab";
          controls.update();
        }
      };
      setModeRef.current = applyMode;

      // --- Auswahl-Highlight ---
      let selectedEntry: CowEntry | null = null;
      function highlight(entry: CowEntry | null) {
        if (selectedEntry && selectedEntry !== entry) {
          selectedEntry.plateMat.emissive.setHex(0x000000);
          selectedEntry.plateMat.emissiveIntensity = 0;
        }
        if (entry) {
          entry.plateMat.emissive.set("#ffd24d");
          entry.plateMat.emissiveIntensity = 0.3;
        }
        selectedEntry = entry;
      }

      // --- Raycast ---
      const raycaster = new THREE.Raycaster();
      raycaster.far = 60;
      const ndc = new THREE.Vector2();
      let down: { x: number; y: number } | null = null;
      let lookLast: { x: number; y: number } | null = null;

      function pickEntry(clientX: number, clientY: number): CowEntry | null {
        const rect = renderer.domElement.getBoundingClientRect();
        ndc.x = ((clientX - rect.left) / rect.width) * 2 - 1;
        ndc.y = -((clientY - rect.top) / rect.height) * 2 + 1;
        raycaster.setFromCamera(ndc, camera);
        const hits = raycaster.intersectObjects(
          cows.map((c) => c.group),
          true,
        );
        if (hits.length === 0) return null;
        let obj: THREE.Object3D | null = hits[0].object;
        while (obj && !obj.userData?.nr) obj = obj.parent;
        return cows.find((c) => c.group === obj) ?? null;
      }

      function onPointerDown(e: PointerEvent) {
        down = { x: e.clientX, y: e.clientY };
        lookLast = { x: e.clientX, y: e.clientY };
        if (modeRef.current === "walk")
          renderer.domElement.style.cursor = "grabbing";
      }
      function onPointerUp(e: PointerEvent) {
        const start = down;
        down = null;
        lookLast = null;
        if (!start) return;
        const dist = Math.hypot(e.clientX - start.x, e.clientY - start.y);
        if (modeRef.current === "walk")
          renderer.domElement.style.cursor = "crosshair";
        if (dist > 6) return; // war ein Drag, kein Klick
        const entry = pickEntry(e.clientX, e.clientY);
        if (entry) {
          highlight(entry);
          setSelected(entry.kuh);
          setHover(null);
        }
      }

      let hoverPending: { x: number; y: number } | null = null;
      let hoverRaf = 0;
      function onPointerMove(e: PointerEvent) {
        // Im Begehen-Modus: Ziehen = Umschauen
        if (modeRef.current === "walk" && down && lookLast) {
          const dx = e.clientX - lookLast.x;
          const dy = e.clientY - lookLast.y;
          lookLast = { x: e.clientX, y: e.clientY };
          euler.setFromQuaternion(camera.quaternion);
          euler.y -= dx * 0.0026;
          euler.x -= dy * 0.0026;
          euler.x = Math.max(-1.2, Math.min(1.2, euler.x));
          camera.quaternion.setFromEuler(euler);
          return;
        }
        if (down) return;
        hoverPending = { x: e.clientX, y: e.clientY };
        if (hoverRaf) return;
        hoverRaf = requestAnimationFrame(() => {
          hoverRaf = 0;
          if (!hoverPending) return;
          const { x, y } = hoverPending;
          hoverPending = null;
          const entry = pickEntry(x, y);
          if (entry) {
            if (modeRef.current === "orbit")
              renderer.domElement.style.cursor = "pointer";
            const rect = renderer.domElement.getBoundingClientRect();
            setHover({ kuh: entry.kuh, x: x - rect.left, y: y - rect.top });
          } else {
            if (modeRef.current === "orbit")
              renderer.domElement.style.cursor = "grab";
            setHover(null);
          }
        });
      }
      function onPointerLeave() {
        setHover(null);
      }
      renderer.domElement.addEventListener("pointerdown", onPointerDown);
      renderer.domElement.addEventListener("pointerup", onPointerUp);
      renderer.domElement.addEventListener("pointermove", onPointerMove);
      renderer.domElement.addEventListener("pointerleave", onPointerLeave);

      // Tastatur (WASD / Pfeile)
      const keys = new Set<string>();
      const onKeyDown = (e: KeyboardEvent) => {
        keys.add(e.key.toLowerCase());
        updateKeyMove();
      };
      const onKeyUp = (e: KeyboardEvent) => {
        keys.delete(e.key.toLowerCase());
        updateKeyMove();
      };
      const updateKeyMove = () => {
        const f =
          (keys.has("w") || keys.has("arrowup") ? 1 : 0) -
          (keys.has("s") || keys.has("arrowdown") ? 1 : 0);
        const s =
          (keys.has("d") || keys.has("arrowright") ? 1 : 0) -
          (keys.has("a") || keys.has("arrowleft") ? 1 : 0);
        if (f !== 0 || s !== 0) moveRef.current = { f, s };
        else if (!moveRef.current.f && !moveRef.current.s)
          moveRef.current = { f: 0, s: 0 };
        else moveRef.current = { f, s };
      };
      window.addEventListener("keydown", onKeyDown);
      window.addEventListener("keyup", onKeyUp);

      // --- Resize ---
      const onResize = () => {
        if (!mount) return;
        const w = mount.clientWidth;
        const h = mount.clientHeight;
        camera.aspect = w / h;
        camera.updateProjectionMatrix();
        renderer.setSize(w, h);
      };
      const ro = new ResizeObserver(onResize);
      ro.observe(mount);

      // --- Loop ---
      let raf = 0;
      const clock = new THREE.Clock();
      const fwd = new THREE.Vector3();
      const right = new THREE.Vector3();
      const animate = () => {
        raf = requestAnimationFrame(animate);
        const dt = Math.min(clock.getDelta(), 0.05);
        const t = clock.elapsedTime;

        for (const c of cows) {
          c.marker.position.y = c.markerBaseY + Math.sin(t * 2 + c.kuh.nr) * 0.05;
        }

        if (modeRef.current === "walk") {
          const { f, s } = moveRef.current;
          if (f !== 0 || s !== 0) {
            camera.getWorldDirection(fwd);
            fwd.y = 0;
            fwd.normalize();
            right.crossVectors(fwd, camera.up).normalize();
            const speed = 3.4 * dt;
            const nx = camera.position.x + (fwd.x * f + right.x * s) * speed;
            const nz = camera.position.z + (fwd.z * f + right.z * s) * speed;
            // Begrenzung auf Stall + Block am Futtertisch (z 0.1..1.7)
            const cx = THREE.MathUtils.clamp(nx, -halfW, halfW);
            let cz = THREE.MathUtils.clamp(nz, -barnD / 2 + 1.5, barnD / 2 - 1.5);
            if (cz > 0.1 && cz < 1.9) cz = camera.position.z; // nicht durch den Tisch
            camera.position.x = cx;
            camera.position.z = cz;
            camera.position.y = EYE;
          }
        } else {
          controls.update();
        }
        renderer.render(scene, camera);
      };
      animate();

      cleanup = () => {
        cancelAnimationFrame(raf);
        if (hoverRaf) cancelAnimationFrame(hoverRaf);
        ro.disconnect();
        window.removeEventListener("keydown", onKeyDown);
        window.removeEventListener("keyup", onKeyUp);
        renderer.domElement.removeEventListener("pointerdown", onPointerDown);
        renderer.domElement.removeEventListener("pointerup", onPointerUp);
        renderer.domElement.removeEventListener("pointermove", onPointerMove);
        renderer.domElement.removeEventListener("pointerleave", onPointerLeave);
        controls.dispose();
        geometries.forEach((g) => g.dispose());
        materials.forEach((m) => m.dispose());
        textures.forEach((t) => t.dispose());
        renderer.dispose();
        if (renderer.domElement.parentNode === mount)
          mount.removeChild(renderer.domElement);
        resetViewRef.current = null;
        setModeRef.current = null;
      };
    })();

    return () => {
      disposed = true;
      cleanup?.();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const switchMode = (m: Mode) => {
    setMode(m);
    setModeRef.current?.(m);
  };

  const counts = (
    ["Gesund", "Trächtig", "In Behandlung", "Trockengestellt"] as KuhStatus[]
  ).map((s) => ({ s, n: kuehe.filter((k) => k.status === s).length }));

  return (
    <main className="mx-auto flex min-h-dvh max-w-6xl flex-col px-4 pb-8 pt-5">
      <header className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          <Link
            href="/"
            className="rounded-lg bg-stall-card px-3 py-2 text-sm font-semibold ring-1 ring-white/10 transition active:scale-95"
          >
            ← Live
          </Link>
          <div>
            <h1 className="flex items-center gap-2 text-xl font-bold tracking-tight sm:text-2xl">
              🧊 3D-Stall
            </h1>
            <p className="text-xs text-white/50 sm:text-sm">
              {mode === "walk"
                ? "Begehen: ziehen zum Umschauen · WASD / Steuerkreuz zum Gehen"
                : "Drehen & Zoomen · Kuh anklicken für Details"}
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <div className="flex rounded-xl bg-stall-card p-1 ring-1 ring-white/10">
            <button
              onClick={() => switchMode("orbit")}
              className={`rounded-lg px-3 py-1.5 text-sm font-semibold transition ${
                mode === "orbit" ? "bg-stall-accent text-black" : "text-white/70"
              }`}
            >
              🧭 Übersicht
            </button>
            <button
              onClick={() => switchMode("walk")}
              className={`rounded-lg px-3 py-1.5 text-sm font-semibold transition ${
                mode === "walk" ? "bg-stall-accent text-black" : "text-white/70"
              }`}
            >
              🚶 Begehen
            </button>
          </div>
          {mode === "orbit" && (
            <button
              onClick={() => resetViewRef.current?.()}
              className="rounded-xl bg-stall-card px-3 py-2 text-sm font-semibold ring-1 ring-white/10 transition active:scale-95"
            >
              ⟲ Reset
            </button>
          )}
        </div>
      </header>

      {/* Legende */}
      <div className="mb-3 flex flex-wrap items-center gap-x-4 gap-y-1 text-xs">
        {counts.map(({ s, n }) => (
          <span key={s} className="inline-flex items-center gap-1.5 text-white/60">
            <span
              className="h-2.5 w-2.5 rounded-full"
              style={{ background: STATUS_COLOR[s] }}
            />
            {s} ({n})
          </span>
        ))}
        <span className="ml-auto text-white/40">{kuehe.length} Kühe · Reihe A</span>
      </div>

      {/* 3D-Canvas */}
      <div className="relative overflow-hidden rounded-2xl border border-white/10 bg-[#cdbfa6] shadow-xl">
        <div ref={mountRef} className="h-[68vh] min-h-[440px] w-full" />

        {/* Hover-Tooltip */}
        {hover && !selected && (
          <div
            className="pointer-events-none absolute z-10 whitespace-nowrap rounded-lg border border-white/15 bg-black/80 px-2.5 py-1.5 text-xs text-white shadow-lg backdrop-blur"
            style={{ left: hover.x + 14, top: hover.y + 14 }}
          >
            <div className="flex items-center gap-1.5">
              <span
                className="h-2 w-2 rounded-full"
                style={{ background: STATUS_COLOR[hover.kuh.status] }}
              />
              <span className="font-semibold">{hover.kuh.name}</span>
              <span className="text-white/60">
                Nr. {String(hover.kuh.nr).padStart(2, "0")}
              </span>
            </div>
            <div className="mt-0.5 text-[10px] text-white/70">
              {hover.kuh.status}
            </div>
          </div>
        )}

        {/* Begehen: Steuerkreuz + Fadenkreuz */}
        {mode === "walk" && (
          <>
            <div className="pointer-events-none absolute left-1/2 top-1/2 z-10 -translate-x-1/2 -translate-y-1/2 text-white/40">
              ＋
            </div>
            <DPad onPress={press} onRelease={release} />
          </>
        )}

        {/* Detail-Popup */}
        {selected && (
          <div className="absolute left-4 right-4 top-4 rounded-2xl border border-white/10 bg-stall-card/95 p-5 shadow-2xl backdrop-blur-md sm:left-auto sm:w-80">
            <button
              onClick={() => setSelected(null)}
              aria-label="Schließen"
              className="absolute right-3 top-3 flex h-8 w-8 items-center justify-center rounded-full bg-white/10 text-white/70 hover:bg-white/20"
            >
              ✕
            </button>
            <div className="mb-3 flex items-center gap-3">
              <div className="flex h-16 w-16 shrink-0 items-center justify-center rounded-xl border border-white/10 bg-black/30 text-2xl">
                🐄
              </div>
              <div className="pr-6 text-xl font-bold">{selected.name}</div>
            </div>
            <InfoRow label="Ohrmarke" value={ohrmarkeFor(selected.nr)} />
            <InfoRow
              label="Status"
              value={
                <span className="inline-flex items-center gap-1.5">
                  <span
                    className="h-2.5 w-2.5 rounded-full"
                    style={{ background: STATUS_COLOR[selected.status] }}
                  />
                  {selected.status}
                </span>
              }
            />
            <InfoRow label="Stallplatz" value={`Reihe A, Platz ${selected.nr}`} />
            <InfoRow label="Rasse" value={`${selected.rasse} · ${selected.alter} J.`} />
            <InfoRow label="Laktation" value={`${selected.laktation}.`} />
            <InfoRow
              label="Milch/Tag"
              value={
                selected.milchTagesleistung > 0
                  ? `${selected.milchTagesleistung} l`
                  : "–"
              }
            />
            {selected.kalbungVoraussichtlich && (
              <InfoRow
                label="Kalbung"
                value={`${formatDate(selected.kalbungVoraussichtlich)} (in ${daysUntil(
                  selected.kalbungVoraussichtlich,
                )} T.)`}
              />
            )}
            {selected.notiz && (
              <p className="mt-3 border-t border-white/10 pt-2 text-xs italic text-white/60">
                {selected.notiz}
              </p>
            )}
          </div>
        )}
      </div>

      <p className="mt-4 text-center text-[11px] text-white/30">
        Oberer Stollenhof · 3D-Stallgang · Demo-Herde
      </p>
    </main>
  );
}

function InfoRow({
  label,
  value,
}: {
  label: string;
  value: React.ReactNode;
}) {
  return (
    <div className="my-1.5 flex items-center gap-2 text-sm">
      <span className="min-w-[80px] text-[11px] font-semibold uppercase tracking-wide text-white/40">
        {label}
      </span>
      <span className="font-medium text-white/90">{value}</span>
    </div>
  );
}

/** On-Screen-Steuerkreuz fuer den Begehen-Modus (Touch & Maus). */
function DPad({
  onPress,
  onRelease,
}: {
  onPress: (f: number, s: number) => void;
  onRelease: () => void;
}) {
  const btn =
    "h-12 w-12 rounded-xl bg-black/45 text-white text-lg font-bold backdrop-blur border border-white/15 active:bg-stall-accent active:text-black select-none flex items-center justify-center";
  const mk = (f: number, s: number) => ({
    onPointerDown: (e: React.PointerEvent) => {
      e.preventDefault();
      onPress(f, s);
    },
    onPointerUp: (e: React.PointerEvent) => {
      e.preventDefault();
      onRelease();
    },
    onPointerLeave: () => onRelease(),
    onPointerCancel: () => onRelease(),
  });
  return (
    <div className="absolute bottom-4 left-1/2 z-20 -translate-x-1/2 select-none">
      <div className="grid grid-cols-3 gap-1.5">
        <span />
        <button className={btn} {...mk(1, 0)}>
          ▲
        </button>
        <span />
        <button className={btn} {...mk(0, -1)}>
          ◀
        </button>
        <button className={btn} {...mk(-1, 0)}>
          ▼
        </button>
        <button className={btn} {...mk(0, 1)}>
          ▶
        </button>
      </div>
    </div>
  );
}
