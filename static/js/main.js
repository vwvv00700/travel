/**
* Template Name: Tour
* Template URL: https://bootstrapmade.com/tour-bootstrap-travel-website-template/
* Updated: Jul 01 2025 with Bootstrap v5.3.7
* Author: BootstrapMade.com
* License: https://bootstrapmade.com/license/
*/

(function() {
    "use strict";

    /**
     * Apply .scrolled class to the body as the page is scrolled down
     */
    function toggleScrolled() {
        const selectBody = document.querySelector('body');
        const selectHeader = document.querySelector('#header');
        if (!selectHeader.classList.contains('scroll-up-sticky') && !selectHeader.classList.contains('sticky-top') && !selectHeader.classList.contains('fixed-top')) return;
        window.scrollY > 100 ? selectBody.classList.add('scrolled') : selectBody.classList.remove('scrolled');
    }

    document.addEventListener('scroll', toggleScrolled);
    window.addEventListener('load', toggleScrolled);

    /**
     * Mobile nav toggle
     */
    const mobileNavToggleBtn = document.querySelector('.mobile-nav-toggle');

    function mobileNavToogle() {
        document.querySelector('body').classList.toggle('mobile-nav-active');
        mobileNavToggleBtn.classList.toggle('bi-list');
        mobileNavToggleBtn.classList.toggle('bi-x');
    }
    if (mobileNavToggleBtn) {
        mobileNavToggleBtn.addEventListener('click', mobileNavToogle);
    }

    /**
     * Hide mobile nav on same-page/hash links
     */
    document.querySelectorAll('#navmenu a').forEach(navmenu => {
        navmenu.addEventListener('click', () => {
            if (document.querySelector('.mobile-nav-active')) {
                mobileNavToogle();
            }
        });

    });

    /**
     * Toggle mobile nav dropdowns
     */
    document.querySelectorAll('.navmenu .toggle-dropdown').forEach(navmenu => {
        navmenu.addEventListener('click', function(e) {
            e.preventDefault();
            this.parentNode.classList.toggle('active');
            this.parentNode.nextElementSibling.classList.toggle('dropdown-active');
            e.stopImmediatePropagation();
        });
    });

    /**
     * Preloader
     */
    const preloader = document.querySelector('#preloader');
    if (preloader) {
            window.addEventListener('load', () => {
            preloader.remove();
        });
    }

    /**
     * Scroll top button
     */
    let scrollTop = document.querySelector('.scroll-top');

    function toggleScrollTop() {
        if (scrollTop) {
            window.scrollY > 100 ? scrollTop.classList.add('active') : scrollTop.classList.remove('active');
        }
    }
    scrollTop.addEventListener('click', (e) => {
        e.preventDefault();
            window.scrollTo({
            top: 0,
            behavior: 'smooth'
        });
    });

    window.addEventListener('load', toggleScrollTop);
    document.addEventListener('scroll', toggleScrollTop);

    /**
     * Animation on scroll function and init
     */
    function aosInit() {
        AOS.init({
        duration: 600,
        easing: 'ease-in-out',
        once: true,
        mirror: false
        });
    }
    window.addEventListener('load', aosInit);

    /**
     * Initiate Pure Counter
     */
    new PureCounter();

    /**
     * Init swiper sliders
     */
    function initSwiper() {
        document.querySelectorAll(".init-swiper").forEach(function(swiperElement) {
        let config = JSON.parse(
            swiperElement.querySelector(".swiper-config").innerHTML.trim()
        );

        if (swiperElement.classList.contains("swiper-tab")) {
            initSwiperWithCustomPagination(swiperElement, config);
        } else {
            new Swiper(swiperElement, config);
        }
        });
    }

    window.addEventListener("load", initSwiper);

    /**
     * Initiate glightbox
     */
    const glightbox = GLightbox({
        selector: '.glightbox'
    });

    /**
     * Init isotope layout and filters
     */
    document.querySelectorAll('.isotope-layout').forEach(function(isotopeItem) {
        let layout = isotopeItem.getAttribute('data-layout') ?? 'masonry';
        let filter = isotopeItem.getAttribute('data-default-filter') ?? '*';
        let sort = isotopeItem.getAttribute('data-sort') ?? 'original-order';

        let initIsotope;
        imagesLoaded(isotopeItem.querySelector('.isotope-container'), function() {
            initIsotope = new Isotope(isotopeItem.querySelector('.isotope-container'), {
                itemSelector: '.isotope-item',
                layoutMode: layout,
                filter: filter,
                sortBy: sort
            });
        });

        isotopeItem.querySelectorAll('.isotope-filters li').forEach(function(filters) {
            filters.addEventListener('click', function() {
                isotopeItem.querySelector('.isotope-filters .filter-active').classList.remove('filter-active');
                this.classList.add('filter-active');
                initIsotope.arrange({
                filter: this.getAttribute('data-filter')
            });
                if (typeof aosInit === 'function') {
                    aosInit();
                }
            }, false);
        });

    });

    /**
     * Frequently Asked Questions Toggle
     */
    document.querySelectorAll('.faq-item h3, .faq-item .faq-toggle, .faq-item .faq-header').forEach((faqItem) => {
        faqItem.addEventListener('click', () => {
            faqItem.parentNode.classList.toggle('faq-active');
        });
    });

    document.querySelectorAll('.thema li input[type="checkbox"]').forEach((checkbox) => {
        checkbox.addEventListener('click', function (e) {
            const checkedCount = document.querySelectorAll('.thema li input[type="checkbox"]:checked').length;

            if (checkedCount > 4) {
                e.preventDefault(); // 체크 상태 변경 막기
                alert('여행 테마는 최대 4개까지만 선택할 수 있습니다.');
            }
        });
    }); 

    function setLanguage(langCode) {
        // 현재 전체 경로를 가져옵니다. (예: /ko/travel/diary/1/)
        var fullPath = "{{ request.get_full_path|escapejs }}";
        
        // 경로에서 기존 언어 코드를 제거하거나, 새로운 언어 코드로 대체합니다.
        // 이 로직은 URL 시작 부분의 언어 코드(예: /en/, /ko/)를 처리하도록 설계되었습니다.
        
        var newPath;
        // 1. 현재 언어 코드(/ko/, /en/ 등)를 제거합니다.
        if (fullPath.match(/^\/([a-z]{2,})\//)) { 
            // 언어 코드가 있다면 제거합니다.
            newPath = fullPath.replace(/^\/([a-z]{2,})\//, '/'); 
        } else {
            // 언어 코드가 없다면 (기본 언어), 그대로 둡니다.
            newPath = fullPath;
        }

        // 2. 제거된 경로 앞에 새 언어 코드를 붙여줍니다.
        // Django의 set_language 뷰는 next가 상대 경로일 때 언어 코드를 붙여주므로,
        // 언어 코드를 **제거한 경로만** next에 넣어주면 됩니다! (가장 간단)
        
        // 하지만 안전하게, 현재 언어 코드를 제거한 순수 경로를 넣습니다.
        document.getElementById('next-path').value = newPath;
    }

})();