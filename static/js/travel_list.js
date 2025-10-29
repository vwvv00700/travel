// =============================
// 전역 상태
// =============================

let currentPlanIdx = (typeof INITIAL_PLAN_IDX !== "undefined") ? INITIAL_PLAN_IDX : 0;

const DEFAULT_CENTER = [37.5665, 126.9780];
const DEFAULT_ZOOM = 13;

let map;
let routeLayerGroup;
let lastClickedSpot = null;

// Day별 경로 캐시 (Mapbox Directions 결과)
const directionsCache = {};


// =============================
// 유틸
// =============================

function updateDistanceInfoBox(text) {
    const box = document.getElementById("distanceInfoBox");
    if (!box) return;
    box.textContent = text;
}

// km 라벨 (총 이동거리용)
function metersToKmLabel(meters) {
    if (!meters || isNaN(meters)) return "";
    const km = meters / 1000;
    return `${km.toFixed(2)} km`;
}

// 개별 구간 거리 포맷 (리스트 옆에 붙는 "88 m", "1.2 km" 같은 것)
function formatDistance(meters) {
    if (!meters && meters !== 0) return "";
    if (meters >= 1000) {
        return (meters / 1000).toFixed(1) + " km";
    } else {
        return Math.round(meters) + " m";
    }
}

function getCookie(name) {
    const value = `; ${document.cookie}`;
    const parts = value.split(`; ${name}=`);
    if (parts.length === 2) return parts.pop().split(";").shift();
    return "";
}

// 라디안 변환
function toRad(v){
    return v * Math.PI / 180;
}

// Haversine (두 점 사이 직선거리 m)
// - 리스트 왼쪽 "N번→N+1번 거리" 계산에 사용
function haversineMeters(lat1, lon1, lat2, lon2){
    const R = 6371000; // m
    const dLat = toRad(lat2 - lat1);
    const dLon = toRad(lon2 - lon1);
    const a = Math.sin(dLat/2)**2 +
              Math.cos(toRad(lat1))*Math.cos(toRad(lat2))*
              Math.sin(dLon/2)**2;
    const c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1-a));
    return R * c; // meters
}

// 왼쪽 패널 높이에 맞춰 지도 높이를 동기화
function syncMapHeightToList() {
    const left = document.querySelector(".itinerary-panel");
    const right = document.querySelector(".map-panel");
    const mapEl = document.getElementById("mapArea");
    if (!left || !right || !mapEl) return;

    const h = left.getBoundingClientRect().height;
    right.style.height = h + "px";
    mapEl.style.height = (h - 60) + "px"; // 지도 헤더(탭 영역) 높이만큼 뺌
    if (map) map.invalidateSize();
}


// =============================
// Mapbox Directions API
// =============================

function buildDirectionsURL(waypoints, profile = "driving") {
    if (!waypoints || waypoints.length < 2) return null;
    const coords = waypoints
        .map(pt => `${pt.lng},${pt.lat}`)
        .join(";");

    const base = `https://api.mapbox.com/directions/v5/mapbox/${profile}/${coords}`;
    const params = new URLSearchParams({
        geometries: "geojson",
        overview: "full",
        access_token: MAPBOX_TOKEN,
    });

    return `${base}?${params.toString()}`;
}

/**
 * waypoints: [{lat, lng, ...}, ...] (문자열일 수도 있으니 parse 필요)
 * return:
 *  {
 *    lineCoords: [ [lat,lng], [lat,lng], ... ], // 경로 폴리라인
 *    distanceMeters: number                     // 전체 주행거리(m)
 *  }
 */
async function fetchRouteForDay(waypoints) {
    const url = buildDirectionsURL(waypoints, "driving");
    if (!url) {
        return {
            lineCoords: [],
            distanceMeters: 0,
        };
    }

    try {
        const resp = await fetch(url);
        if (!resp.ok) {
            console.error("Mapbox Directions API error", resp.status, resp.statusText);
            return { lineCoords: [], distanceMeters: 0 };
        }

        const data = await resp.json();
        if (!data.routes || !data.routes.length) {
            return { lineCoords: [], distanceMeters: 0 };
        }

        const best = data.routes[0];
        const coordsLngLat = best.geometry.coordinates || [];
        const distanceMeters = best.distance || 0;

        // Mapbox는 [lng, lat] 이라서 Leaflet은 [lat, lng]로 바꿔야 함
        const lineCoords = coordsLngLat.map(pair => [pair[1], pair[0]]);

        return {
            lineCoords,
            distanceMeters,
        };
    } catch (err) {
        console.error("Directions fetch failed:", err);
        return { lineCoords: [], distanceMeters: 0 };
    }
}


// =============================
// 지도 관련
// =============================

function initMap() {
    if (map) return;
    const mapEl = document.getElementById("mapArea");
    if (!mapEl) {
        console.warn("mapArea element not found");
        return;
    }

    map = L.map(mapEl).setView(DEFAULT_CENTER, DEFAULT_ZOOM);

    // 타일: OSM
    L.tileLayer(
        "https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png",
        {
            maxZoom: 19,
            attribution: "&copy; OpenStreetMap contributors",
        }
    ).addTo(map);

    routeLayerGroup = L.layerGroup().addTo(map);
}

function clearRouteLayers() {
    if (!routeLayerGroup) return;
    routeLayerGroup.clearLayers();
}

// 지도 위 마커 (번호만 있는 동그라미)
function addWaypointsMarkers(mapInstance, waypoints, layerGroup) {
    for (let i = 0; i < waypoints.length; i++) {
        const wp = waypoints[i];
        const latNum = parseFloat(wp.lat);
        const lngNum = parseFloat(wp.lng);
        if (isNaN(latNum) || isNaN(lngNum)) continue;

        const markerHtml = `
            <div class="map-marker-circle">
                <span class="map-marker-number">${i + 1}</span>
            </div>
        `;

        const markerIcon = L.divIcon({
            className: "custom-marker-basic",
            html: markerHtml,
            iconSize: [32, 32],
            iconAnchor: [16, 32],
        });

        const marker = L.marker([latNum, lngNum], { icon: markerIcon })
            .addTo(layerGroup);

        marker.on("click", () => {
            mapInstance.setView([latNum, lngNum], 15);
        });
    }
}

/**
 * dayIdx: 1부터 시작 (Day1 -> 1)
 * - 마커
 * - 경로 polyline
 * - 지도 bounds
 * - 총 이동거리(distanceInfoBox) 업데이트
 */
async function renderMapForDay(dayIdx) {
    if (!PLANS || typeof currentPlanIdx === "undefined") return;
    const planData = PLANS[currentPlanIdx];
    if (!planData) return;

    initMap();
    if (!map) return;
    clearRouteLayers();

    const waypointsByDay = planData.day_waypoints || [];
    const waypoints = waypointsByDay[dayIdx - 1] || [];

    if (!waypoints.length) {
        map.setView(DEFAULT_CENTER, DEFAULT_ZOOM);
        updateDistanceInfoBox("");
        const totalKm = routeData.distanceMeters ? metersToKmLabel(routeData.distanceMeters) : "";
        updateDistanceInfoBox(totalKm ? `예상 이동 거리 약 ${totalKm}` : "");
        const dayTitleEl = document.querySelector(`.day-title[data-day="${dayIdx}"] .day-total-dist`);
        if (dayTitleEl) {
            dayTitleEl.textContent = totalKm ? `(${totalKm})` : "";
        }
        syncMapHeightToList();
        return;
    }

    // 마커들 찍기
    addWaypointsMarkers(map, waypoints, routeLayerGroup);

    // polyline을 그리기 위한 bounds 후보
    const latlngBoundsArr = [];
    waypoints.forEach(pt => {
        const latNum = parseFloat(pt.lat);
        const lngNum = parseFloat(pt.lng);
        if (!isNaN(latNum) && !isNaN(lngNum)) {
            latlngBoundsArr.push([latNum, lngNum]);
        }
    });

    // Mapbox Directions 결과 (캐싱)
    const cacheKey = `${currentPlanIdx}-${dayIdx}`;
    let routeData = directionsCache[cacheKey];
    if (!routeData) {
        routeData = await fetchRouteForDay(waypoints);
        directionsCache[cacheKey] = routeData;
    }

    // polyline 라인 그리기
    if (routeData.lineCoords && routeData.lineCoords.length > 1) {
        L.polyline(routeData.lineCoords, {
            weight: 4,
            color: "#db4040",
            opacity: 0.9,
        }).addTo(routeLayerGroup);

        const combinedBounds = [
            ...latlngBoundsArr,
            ...routeData.lineCoords,
        ];
        map.fitBounds(combinedBounds, { padding: [20, 20] });
    } else {
        // fallback: 좌표만으로 fit
        if (latlngBoundsArr.length === 1) {
            map.setView(latlngBoundsArr[0], 15);
        } else if (latlngBoundsArr.length > 1) {
            map.fitBounds(latlngBoundsArr, { padding: [20, 20] });
        } else {
            map.setView(DEFAULT_CENTER, DEFAULT_ZOOM);
        }
    }

    // 총 이동거리 박스 업데이트
    if (routeData.distanceMeters && routeData.distanceMeters > 0) {
        updateDistanceInfoBox(
            `예상 이동 거리 약 ${metersToKmLabel(routeData.distanceMeters)}`
        );
    } else if (waypoints.length === 1) {
        updateDistanceInfoBox("단일 위치 안내");
    } else {
        updateDistanceInfoBox("");
    }

    syncMapHeightToList();
}


// =============================
// 왼쪽 리스트 렌더
// =============================

/**
 * planIdx 플랜의 day_plans 구조를 읽어서
 * #itineraryContainer 안을 전부 다시 만든다.
 *
 * 각 spot-item 안:
 *   .spot-order-num  -> 순번
 *   .spot-order-dist -> 이전 지점에서 여기까지의 거리
 */
function renderItineraryListFromPlan(planIdx) {
    if (!PLANS) return;
    const planData = PLANS[planIdx];
    if (!planData) return;

    const container = document.getElementById("itineraryContainer");
    if (!container) return;

    const allDays = planData.day_plans || [];

    let html = "";

    allDays.forEach((dayStops, dayIndex) => {
        html += `
            <div class="day-block">
                <div class="day-title" data-day="${dayIndex + 1}">
                    Day ${dayIndex + 1}
                    <span class="day-total-dist"></span>
                </div>
        `;

        if (dayStops && dayStops.length) {
            for (let i = 0; i < dayStops.length; i++) {
                const stop = dayStops[i] || {};
                const name = stop.name || "";
                const category = stop.category || "";
                const address = stop.address || "";
                const themes_csv = stop.themes_csv || "";
                const group_couple = stop.group_couple ? `· 커플선호 ${stop.group_couple}` : "";
                const season_autumn = stop.season_autumn ? `· 가을매력 ${stop.season_autumn}` : "";

                // i -> i+1 거리 (마지막 아이템은 없음)
                let distText = "";
                if (i < dayStops.length - 1) {
                    const next = dayStops[i + 1];
                    const meters = haversineMeters(
                        parseFloat(stop.lat), parseFloat(stop.lng),
                        parseFloat(next.lat), parseFloat(next.lng)
                    );
                    distText = formatDistance(meters);
                }

                html += `
                <div class="spot-item"
                     data-day="${dayIndex + 1}"
                     data-order="${i}"
                     data-lat="${stop.lat || ""}"
                     data-lng="${stop.lng || ""}">
                    
                    <div class="spot-order">
                        <div class="spot-order-num">${i + 1}</div>
                        ${
                            distText
                            ? `<div class="spot-order-dist">${distText}</div>`
                            : ``
                        }
                    </div>

                    <div class="spot-meta">
                        <div class="spot-name">
                            ${name}
                            <span class="spot-cat">(${category})</span>
                        </div>
                        <p class="spot-desc">
                            ${themes_csv}
                            ${group_couple}
                            ${season_autumn}
                        </p>
                        ${address
                            ? `<p class="spot-desc spot-addr">${address}</p>`
                            : ``
                        }
                    </div>

                </div>
                `;
            }
        } else {
            html += `
                <div class="spot-desc">추천 장소가 부족합니다.</div>
            `;
        }

        html += `</div>`;
    });

    container.innerHTML = html;
}


// =============================
// 이벤트 바인딩 (리스트 클릭, Day 탭, 플랜 선택 등)
// =============================

// 왼쪽 장소 카드 클릭 시:
// - 첫 클릭: 해당 지점으로 지도 줌
// - 같은 카드 다시 클릭: Day 전체 경로로 리셋
function attachSpotClickHandler() {
    const scrollArea = document.getElementById("itineraryContainer");
    if (!scrollArea) return;

    scrollArea.addEventListener("click", (e) => {
        const item = e.target.closest(".spot-item");
        if (!item) return;
        if (!map) return;

        const lat = parseFloat(item.dataset.lat);
        const lng = parseFloat(item.dataset.lng);

        if (isNaN(lat) || isNaN(lng)) {
            map.setView(DEFAULT_CENTER, DEFAULT_ZOOM);
            lastClickedSpot = null;
            return;
        }

        if (lastClickedSpot === item) {
            const dayIdx = parseInt(item.dataset.day, 10) || 1;
            renderMapForDay(dayIdx);
            lastClickedSpot = null;
        } else {
            map.setView([lat, lng], 15);
            lastClickedSpot = item;
        }
    });
}

// Day 탭 클릭 -> 해당 Day 경로/거리 지도에 반영
function bindDayTabs() {
    const tabsWrap = document.getElementById("dayTabs");
    if (!tabsWrap) return;

    const buttons = tabsWrap.querySelectorAll(".day-tab-btn");
    buttons.forEach(btn => {
        btn.addEventListener("click", () => {
            buttons.forEach(b => b.classList.remove("active"));
            btn.classList.add("active");

            const d = parseInt(btn.getAttribute("data-day"), 10) || 1;
            renderMapForDay(d);
            lastClickedSpot = null;
        });
    });
}

// 플랜 바뀌면 Day 탭 자체도 다시 만들어야 한다
function redrawDayTabsFromPlans() {
    const tabsWrap = document.getElementById("dayTabs");
    if (!tabsWrap) return;
    if (!PLANS || typeof currentPlanIdx === "undefined") return;
    const planData = PLANS[currentPlanIdx];
    if (!planData) return;

    const dayPlans = planData.day_plans || [];
    let html = "";
    dayPlans.forEach((_, idx) => {
        html += `
        <button
            class="day-tab-btn ${idx === 0 ? "active" : ""}"
            data-day="${idx + 1}">
            Day ${idx + 1}
        </button>`;
    });

    tabsWrap.innerHTML = html;
    bindDayTabs(); // 새 버튼들에 이벤트 다시 부여
}

function updateGuideText() {
    const guideEl = document.getElementById("guideText");
    if (!guideEl) return;
    if (!PLANS || typeof currentPlanIdx === "undefined") return;
    const planData = PLANS[currentPlanIdx];
    if (!planData) return;
    guideEl.textContent = planData.guide_text || "가이드를 불러오는 중입니다...";
}

// 저장하기 버튼이 현재 플랜 id랑 맞게 동기화
function syncSaveButtonPlanId() {
    const saveBtn = document.getElementById("savePlanBtn");
    if (!saveBtn) return;
    if (!PLANS || typeof currentPlanIdx === "undefined") return;
    const planData = PLANS[currentPlanIdx];
    if (!planData) return;
    saveBtn.dataset.planId = planData.id;
}

// 플랜 선택 버튼 (추천 플랜들 탭)
function bindPlanSelector() {
    const selector = document.getElementById("planSelector");
    if (!selector) return;

    const buttons = selector.querySelectorAll(".plan-label-btn");
    buttons.forEach(btn => {
        btn.addEventListener("click", () => {
            const idx = parseInt(btn.getAttribute("data-plan-idx"), 10);
            currentPlanIdx = isNaN(idx) ? 0 : idx;

            // 플랜 버튼 active 토글
            buttons.forEach(b => b.classList.remove("active"));
            btn.classList.add("active");

            // 왼쪽 Day 리스트 다시 그림 (번호+구간거리까지 반영)
            renderItineraryListFromPlan(currentPlanIdx);

            // 새 리스트에 클릭 이벤트 다시 연결
            attachSpotClickHandler();

            // 가이드 텍스트 갱신
            updateGuideText();

            // Day 탭 갱신 후 Day1 활성화 상태
            redrawDayTabsFromPlans();

            // 지도 Day1 및 총 이동거리 갱신
            renderMapForDay(1);

            // 저장 버튼 plan_id 갱신
            syncSaveButtonPlanId();

            // 왼쪽 스크롤 맨 위로
            const scrollArea = document.getElementById("itineraryContainer");
            if (scrollArea) scrollArea.scrollTop = 0;
        });
    });
}


// =============================
// 저장 버튼 ajax
// =============================

function setupSaveButton() {
    const saveBtn = document.getElementById("savePlanBtn");
    if (!saveBtn) return;

    saveBtn.addEventListener("click", () => {
        const planId = saveBtn.dataset.planId;

        fetch("/travel/select_plan/", {
            method: "POST",
            headers: {
                "Content-Type": "application/x-www-form-urlencoded",
                "X-CSRFToken": getCookie("csrftoken"),
            },
            body: `plan_id=${encodeURIComponent(planId)}`
        })
        .then(res => res.json())
        .then(data => {
            if (data.status === "success") {
                alert("플랜이 내 여행으로 저장됐어요 ✅");
            } else if (data.status === "login_required") {
                alert("로그인 후에 저장할 수 있어요.");
                window.location.href = "/travel/login/";
            } else {
                alert("저장 중 오류가 발생했어요.");
            }
        })
        .catch(err => {
            console.error(err);
            alert("서버 오류가 발생했어요.");
        });
    });
}


// =============================
// 초기 구동
// =============================

window.addEventListener("DOMContentLoaded", () => {
    // 1. 지도 초기화
    initMap();

    // 2. 현재 플랜 기준으로
    //    - 왼쪽 Day 리스트(번호/구간거리 포함) 렌더
    //    - spot 클릭 핸들러
    renderItineraryListFromPlan(currentPlanIdx);
    attachSpotClickHandler();

    // 3. 가이드 텍스트 갱신
    updateGuideText();

    // 4. Day 탭 그리기 + 첫 번째 Day 활성화
    redrawDayTabsFromPlans();
    bindDayTabs();

    // 5. 지도 Day1 렌더 (마커/라인/총 이동거리 distanceInfoBox 표시)
    renderMapForDay(1);

    // 6. 저장하기 버튼 동기화 + 클릭 이벤트
    syncSaveButtonPlanId();
    setupSaveButton();

    // 7. 플랜 선택 버튼 (다른 추천 플랜 눌렀을 때 전부 다시 세팅)
    bindPlanSelector();

    // 8. 레이아웃 높이 동기화
    syncMapHeightToList();
});
