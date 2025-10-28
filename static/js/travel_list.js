// =============================
// travel_list.js (MAPBOX DIRECTIONS VERSION)
// =============================

// 기본 중심 좌표 (서울 시청 근처 정도)
const DEFAULT_CENTER = [37.5665, 126.9780];
const DEFAULT_ZOOM = 13;

// Leaflet 전역 객체
let map;
let routeLayerGroup;

// 마지막으로 클릭했던 장소 DOM
let lastClickedSpot = null;

// Directions cache: { "<planIdx>-<dayIdx>": {geojson:..., distanceKm:...} }
const directionsCache = {};


// ---------- 공통 유틸 ----------

function updateDistanceInfoBox(text) {
    const box = document.getElementById("distanceInfoBox");
    if (!box) return;
    box.textContent = text;
}

/**
 * m(미터) -> "x.xx km"
 */
function metersToKmLabel(meters) {
    if (!meters || isNaN(meters)) return "";
    const km = meters / 1000;
    return `${km.toFixed(2)} km`;
}


// ---------- Mapbox Directions API ----------

/**
 * 하나의 Day(waypoints 배열)를 받아
 * Mapbox Directions API URL을 만든다.
 *
 * waypoints: [ {lat:..., lng:...}, {lat:..., lng:...}, ... ]
 * profile: "driving", "walking", "cycling" 등 (여기선 driving 가정)
 *
 * NOTE:
 * - Mapbox Directions API는 최소 2개의 좌표 필요.
 * - 경유지 여러 개 가능: /coords;coords;coords
 */
function buildDirectionsURL(waypoints, profile = "driving") {
    if (!waypoints || waypoints.length < 2) return null;
    const coords = waypoints
        .map(pt => `${pt.lng},${pt.lat}`) // lng,lat 순서 중요
        .join(";");

    // steps=false로 한 번에 큰 라인(overview)만 받아도 되고
    // overview=full 로 최대한 자세한 경로를 요청
    const base = `https://api.mapbox.com/directions/v5/mapbox/${profile}/${coords}`;
    const params = new URLSearchParams({
        geometries: "geojson",
        overview: "full",
        access_token: MAPBOX_TOKEN,
    });

    return `${base}?${params.toString()}`;
}

/**
 * Directions API 호출해서 GeoJSON LineString과 총 이동거리(m)를 얻는다.
 * 반환:
 *   { lineCoords: [[lat,lng], ...], distanceMeters: number }
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

        // Mapbox 응답 구조:
        // data.routes[0].geometry.coordinates = [[lng,lat],[lng,lat],...]
        // data.routes[0].distance = 총 거리 (m)
        if (!data.routes || !data.routes.length) {
            return { lineCoords: [], distanceMeters: 0 };
        }

        const best = data.routes[0];
        const coordsLngLat = best.geometry.coordinates || [];
        const distanceMeters = best.distance || 0;

        // Leaflet polyline은 [lat,lng] 필요하므로 변환
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


// ---------- 지도 초기화 / 라우팅 ----------

function initMap() {
    if (map) return; // 이미 초기화했으면 스킵

    const mapEl = document.getElementById("mapArea");
    if (!mapEl) {
        console.warn("mapArea element not found");
        return;
    }

    map = L.map(mapEl).setView(DEFAULT_CENTER, DEFAULT_ZOOM);

    // 타일은 OSM 기본 유지 (원하면 Mapbox 스타일 타일로 교체 가능)
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

/**
 * 현재 currentPlanIdx, 선택 dayIdx(1부터 시작)
 * => PLANS[currentPlanIdx].day_waypoints[dayIdx-1] 를 이용해
 *    Mapbox Directions API로 실제 경로 polyline을 그림.
 *
 * 마커는 각 스톱마다 번호 divIcon으로 표시.
 */
async function renderMapForDay(dayIdx) {
    if (!PLANS || typeof currentPlanIdx === "undefined") return;
    const planData = PLANS[currentPlanIdx];
    if (!planData) return;

    initMap();
    if (!map) return;
    clearRouteLayers();

    const dayWaypointsAll = planData.day_waypoints || [];
    const waypoints = dayWaypointsAll[dayIdx - 1] || [];

    if (!waypoints.length) {
        map.setView(DEFAULT_CENTER, DEFAULT_ZOOM);
        updateDistanceInfoBox("위치 좌표 없음");
        return;
    }

    // 1) 모든 스팟에 번호 마커 찍기
    const latlngBoundsArr = [];
    waypoints.forEach((pt, i) => {
        const latNum = parseFloat(pt.lat);
        const lngNum = parseFloat(pt.lng);
        if (isNaN(latNum) || isNaN(lngNum)) return;

        latlngBoundsArr.push([latNum, lngNum]);

        // 번호 마커(divIcon)
        const markerIcon = L.divIcon({
            className: "",
            html: `
                <div style="
                    width:28px;
                    height:28px;
                    border-radius:50%;
                    background:#db4040;
                    color:#fff;
                    font-size:0.8rem;
                    font-weight:600;
                    display:flex;
                    align-items:center;
                    justify-content:center;
                    border:2px solid #fff;
                    box-shadow:0 0 4px rgba(0,0,0,.4);
                ">${i + 1}</div>
            `,
            iconSize: [28, 28],
            iconAnchor: [14, 14],
        });

        const marker = L.marker([latNum, lngNum], { icon: markerIcon })
            .addTo(routeLayerGroup);

        // 마커 클릭: 해당 좌표로 줌
        marker.on("click", () => {
            map.setView([latNum, lngNum], 15);
        });
    });

    // 2) Directions API 호출 (cache 먼저 확인)
    const cacheKey = `${currentPlanIdx}-${dayIdx}`;
    let routeData = directionsCache[cacheKey];

    if (!routeData) {
        routeData = await fetchRouteForDay(waypoints);
        directionsCache[cacheKey] = routeData;
    }

    // 3) 경로 polyline 그리기
    if (routeData.lineCoords && routeData.lineCoords.length > 1) {
        L.polyline(routeData.lineCoords, {
            weight: 4,
            color: "#db4040",
            opacity: 0.9,
        }).addTo(routeLayerGroup);

        // bounds에 라우트까지 포함
        const combinedBounds = [...latlngBoundsArr, ...routeData.lineCoords];
        map.fitBounds(combinedBounds, { padding: [20, 20] });
    } else {
        // fallback: 여러 점 없으면 첫 점으로 이동
        if (latlngBoundsArr.length === 1) {
            map.setView(latlngBoundsArr[0], 15);
        } else if (latlngBoundsArr.length > 1) {
            map.fitBounds(latlngBoundsArr, { padding: [20, 20] });
        } else {
            map.setView(DEFAULT_CENTER, DEFAULT_ZOOM);
        }
    }

    // 4) 총 이동거리 UI 업데이트
    if (routeData.distanceMeters && routeData.distanceMeters > 0) {
        updateDistanceInfoBox(
            `예상 이동 거리 약 ${metersToKmLabel(routeData.distanceMeters)}`
        );
    } else if (waypoints.length === 1) {
        updateDistanceInfoBox("단일 위치 안내");
    } else {
        updateDistanceInfoBox("이동 거리 계산 불가");
    }
}


// ---------- 왼쪽 일정 리스트 렌더 ----------

/**
 * 현재 currentPlanIdx 의 day_plans(=각 Day의 장소들)을
 * itineraryContainer 안에 다시 그린다.
 *  + 맨 위에 추천 플랜 버튼들도 다시 그린다.
 */
function renderItineraryList() {
    if (!PLANS || typeof currentPlanIdx === "undefined") return;
    const container = document.getElementById("itineraryContainer");
    if (!container) return;

    const planData = PLANS[currentPlanIdx];
    if (!planData) return;

    const dayPlans = planData.day_plans || [];

    // 1) 추천 플랜 버튼 렌더
    let html = `<div class="plan-selector" id="planSelector">`;
    PLANS.forEach((plan, idx) => {
        html += `
        <button
            class="plan-label-btn ${idx === currentPlanIdx ? "active" : ""}"
            data-plan-idx="${idx}">
            ${plan.name || ("플랜 " + (idx+1))}
        </button>`;
    });
    html += `</div>`;

    // 2) Day별 블록 렌더
    dayPlans.forEach((stops, dayIdx) => {
        html += `<div class="day-block">`;
        html += `<div class="day-title">Day ${dayIdx + 1}</div>`;

        if (stops && stops.length > 0) {
            stops.forEach((stop, orderIdx) => {
                const couple = stop.group_couple ? ` · 커플선호 ${stop.group_couple}` : "";
                const autumn = stop.season_autumn ? ` · 가을매력 ${stop.season_autumn}` : "";
                const addrHtml = stop.address
                    ? `<p class="spot-desc" style="margin-top:4px;">${stop.address}</p>`
                    : "";

                html += `
                <div class="spot-item"
                     data-day="${dayIdx + 1}"
                     data-order="${orderIdx}"
                     data-lat="${stop.lat || ""}"
                     data-lng="${stop.lng || ""}">
                    <div class="spot-order">${orderIdx + 1}</div>
                    <div class="spot-meta">
                        <div class="spot-name">
                            ${stop.name}
                            <span style="font-weight:400;color:#888;font-size:0.7rem;">
                                (${stop.category})
                            </span>
                        </div>
                        <p class="spot-desc">
                            ${stop.themes_csv || ""}${couple}${autumn}
                        </p>
                        ${addrHtml}
                    </div>
                </div>`;
            });
        } else {
            html += `<div class="spot-desc">추천 장소가 부족합니다.</div>`;
        }

        html += `</div>`; // .day-block
    });

    container.innerHTML = html;

    // 리스트 다시 그렸으니까 플랜 버튼 클릭 핸들러 재장착
    setupPlanSelector();
}


/**
 * 장소 클릭 핸들러(지도 줌 / 다시 Day 경로 복귀)
 * 전역에 한 번만 붙인다.
 */
function attachSpotClickHandler() {
    document.addEventListener("click", (e) => {
        const item = e.target.closest(".spot-item");
        if (!item) return;
        if (!map) return;

        const lat = parseFloat(item.dataset.lat);
        const lng = parseFloat(item.dataset.lng);

        if (isNaN(lat) || isNaN(lng)) {
            // 좌표 없으면 전체 뷰 복귀
            map.setView(DEFAULT_CENTER, DEFAULT_ZOOM);
            lastClickedSpot = null;
            return;
        }

        if (lastClickedSpot === item) {
            // 같은 곳 다시 누르면 Day 경로 전체로 복귀
            const dayIdx = parseInt(item.dataset.day, 10) || 1;
            renderMapForDay(dayIdx);
            lastClickedSpot = null;
        } else {
            // 해당 장소로 줌
            map.setView([lat, lng], 15);
            lastClickedSpot = item;
        }
    });
}


// ---------- Day 탭 렌더 ----------

/**
 * 현재 플랜의 day_plans 길이에 맞게 Day1 / Day2 ... 버튼 다시 그림
 * 클릭하면 그 Day의 경로로 지도 redraw
 */
function renderDayTabs() {
    if (!PLANS || typeof currentPlanIdx === "undefined") return;
    const tabsWrap = document.getElementById("dayTabs");
    if (!tabsWrap) return;

    const planData = PLANS[currentPlanIdx];
    if (!planData) return;

    const dayPlans = planData.day_plans || [];

    let html = "";
    dayPlans.forEach((_, dayIdx) => {
        html += `
        <button class="day-tab-btn ${dayIdx === 0 ? "active" : ""}"
                data-day="${dayIdx + 1}">
            Day ${dayIdx + 1}
        </button>`;
    });

    tabsWrap.innerHTML = html;

    // 이벤트 바인딩
    const buttons = tabsWrap.querySelectorAll(".day-tab-btn");
    buttons.forEach(btn => {
        btn.addEventListener("click", () => {
            // active 토글
            buttons.forEach(b => b.classList.remove("active"));
            btn.classList.add("active");

            // 해당 Day 경로 지도에 그림
            const d = parseInt(btn.getAttribute("data-day"), 10) || 1;
            renderMapForDay(d);
            lastClickedSpot = null;
        });
    });
}


// ---------- 가이드 텍스트 렌더 ----------

function renderGuideText() {
    if (!PLANS || typeof currentPlanIdx === "undefined") return;
    const guideEl = document.getElementById("guideText");
    if (!guideEl) return;

    const planData = PLANS[currentPlanIdx];
    if (!planData) return;

    guideEl.textContent =
        planData.guide_text ||
        "가이드를 불러오는 중입니다...";
}


// ---------- 플랜 선택 버튼 동작 ----------

/**
 * plan-selector 안의 .plan-label-btn 들에 클릭 이벤트를 단다.
 * -> currentPlanIdx 바꾸고 전체 다시 그리기
 */
function setupPlanSelector() {
    const selector = document.getElementById("planSelector");
    if (!selector) return;

    const buttons = selector.querySelectorAll(".plan-label-btn");

    buttons.forEach(btn => {
        btn.addEventListener("click", () => {
            const idx = parseInt(btn.getAttribute("data-plan-idx"), 10);
            currentPlanIdx = isNaN(idx) ? 0 : idx;

            // 전체 리렌더
            renderItineraryList();  // 왼쪽 리스트 + 플랜 버튼 다시 그림
            renderGuideText();      // 가이드 갱신
            renderDayTabs();        // Day 탭 갱신
            renderMapForDay(1);     // 지도 Day1 경로 갱신
            lastClickedSpot = null;

            // UX: 왼쪽 패널 맨 위로 스크롤
            const panel = document.getElementById("itineraryContainer");
            if (panel) panel.scrollTop = 0;
        });
    });
}


// ---------- 초기 구동 ----------

window.addEventListener("DOMContentLoaded", () => {
    // 지도 먼저 준비
    initMap();

    // 첫 화면 렌더 (initial_plan_idx 값 기반으로 전역 currentPlanIdx는
    // Django 템플릿에서 만들어준다고 가정)
    renderItineraryList();  // 왼쪽 + 플랜버튼
    renderGuideText();      // 가이드
    renderDayTabs();        // Day 탭
    renderMapForDay(1);     // 지도 Day1 (Directions fetch 포함)

    // 전역 클릭 핸들러(spot-item용) 한 번만 세팅
    attachSpotClickHandler();
});
