import { useEffect, useRef, useState } from "react";

const painPoints = [
  {
    title: "Saatler süren tasarım",
    text: "Ürün görseli bul, arka planı temizle, fiyat etiketi hazırla, Canva'da yerleştir. Her hafta 2-6 saat.",
  },
  {
    title: "Her fiyat değişikliğinde baştan",
    text: "Tek bir fiyat güncellemesi bile tüm tasarımı yeniden açıp düzenlemek demek.",
  },
  {
    title: "Her kanal için ayrı format",
    text: "Baskı için PDF, WhatsApp için görsel, Instagram için kare post. Hepsi ayrı ayrı elle üretiliyor.",
  },
];

const steps = [
  {
    title: "Listenizi gönderin",
    text: "Ürün ve fiyat listenizi Telegram veya WhatsApp'tan mesaj olarak yazın. Excel de gönderebilirsiniz.",
  },
  {
    title: "Sistem broşürü hazırlasın",
    text: "Ürünler katalogla eşleştirilir, görseller ve fiyat etiketleri seçtiğiniz şablona otomatik yerleştirilir.",
  },
  {
    title: "Onaylayın, dosyalar elinizde",
    text: "Önizlemeyi onaylayın; baskıya hazır A4 PDF ve sosyal medya görselleri dakikalar içinde size gönderilir.",
  },
];

const featureIcons = {
  catalog: (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round">
      <path d="M4 5.5A2.5 2.5 0 0 1 6.5 3H20v15.5H6.5A2.5 2.5 0 0 0 4 21z" />
      <path d="M4 18.5A2.5 2.5 0 0 1 6.5 16H20" />
      <path d="M9 7.5h7" />
    </svg>
  ),
  match: (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="10.5" cy="10.5" r="6.5" />
      <path d="m20 20-4.4-4.4" />
      <path d="m8 10.6 1.8 1.8 3.2-3.4" />
    </svg>
  ),
  template: (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round">
      <rect x="3.5" y="3.5" width="17" height="17" rx="2.5" />
      <path d="M3.5 9h17" />
      <path d="M9.5 9v11.5" />
    </svg>
  ),
  files: (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round">
      <path d="M13.5 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8.5z" />
      <path d="M13.5 3v5.5H19" />
      <path d="M9 13h6M9 16.5h6" />
    </svg>
  ),
  approve: (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round">
      <path d="M12 21c4.97-2.2 8-5.6 8-10V6l-8-3-8 3v5c0 4.4 3.03 7.8 8 10z" />
      <path d="m8.8 11.6 2.3 2.3 4.1-4.4" />
    </svg>
  ),
  panel: (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round">
      <rect x="3.5" y="4.5" width="17" height="15" rx="2.5" />
      <path d="M3.5 9.5h17" />
      <path d="M8 14h4M8 16.5h6.5" />
    </svg>
  ),
};

const features = [
  {
    icon: "catalog",
    title: "Ürün kataloğu",
    text: "Ürünleriniz görselleri ve markalarıyla bir kez kaydedilir, her kampanyada hazır bekler.",
  },
  {
    icon: "match",
    title: "Akıllı eşleştirme",
    text: "\"Cocacola 2lt\" yazsanız da doğru ürünü bulur; emin olamadıklarını onayınıza sunar.",
  },
  {
    icon: "template",
    title: "Hazır şablonlar",
    text: "Profesyonel tasarlanmış broşür şablonları. Rastgele tasarım yok, her hafta tutarlı görünüm.",
  },
  {
    icon: "files",
    title: "PDF + Instagram görseli",
    text: "Tek listeden baskıya hazır A4 PDF, paylaşıma hazır PNG ve Instagram postu birlikte üretilir.",
  },
  {
    icon: "approve",
    title: "Önizleme ve onay",
    text: "Hiçbir broşür siz onaylamadan yayınlanmaz. Revizyon isteğinizi mesajla iletmeniz yeterli.",
  },
  {
    icon: "panel",
    title: "Yönetim paneli",
    text: "Kampanyalarınızı, ürünlerinizi ve geçmiş broşürlerinizi tek panelden takip edin.",
  },
];

const plans = [
  {
    name: "Başlangıç",
    price: "59€",
    tagline: "Tek şubeli küçük marketler için",
    items: ["Ayda 4 kampanya", "2 broşür şablonu", "A4 PDF + PNG çıktı", "Telegram üzerinden kullanım"],
    highlighted: false,
  },
  {
    name: "Standart",
    price: "119€",
    tagline: "Düzenli kampanya yapan marketler için",
    items: [
      "Ayda 10 kampanya",
      "Tüm broşür şablonları",
      "A4 PDF + PNG + Instagram postu",
      "Öncelikli destek",
    ],
    highlighted: true,
  },
  {
    name: "Pro",
    price: "199€",
    tagline: "Zincir ve yoğun kullanım için",
    items: ["Sınırsız kampanya", "Özel şablon çalışması", "Tüm çıktı formatları", "Telefonla destek"],
    highlighted: false,
  },
];

const faqs = [
  {
    q: "Nasıl başlarım?",
    a: "Ücretsiz deneme talebinizi iletin; ürünlerinizi katalogunuza biz ekleyelim. İlk kampanya listenizi gönderdiğinizde ilk broşürünüz ücretsiz hazırlanır.",
  },
  {
    q: "Hangi uygulamalardan liste gönderebilirim?",
    a: "İlk aşamada Telegram desteklenir; WhatsApp desteği yol haritamızda. Listeyi düz mesaj olarak yazmanız yeterlidir.",
  },
  {
    q: "Ürün görsellerini nereden bulacağım?",
    a: "Katalog kurulumunda yaygın markaların görselleri bizim tarafımızdan eklenir. Kendi ürünleriniz için fotoğraf göndermeniz yeterli.",
  },
  {
    q: "Tasarım bilgim yok, sorun olur mu?",
    a: "Hayır. Şablonlar profesyonelce tasarlanmıştır; siz yalnızca ürün ve fiyat listesini gönderirsiniz.",
  },
  {
    q: "İstediğim zaman iptal edebilir miyim?",
    a: "Evet. Aylık paketlerde taahhüt yoktur, dilediğiniz ay durdurabilirsiniz.",
  },
];

const productArt = {
  sucuk: (
    <svg viewBox="0 0 64 64">
      <circle cx="24" cy="27" r="16" fill="#7e2f21" />
      <circle cx="24" cy="27" r="12.5" fill="#e9d8c4" />
      <g fill="#a44a33">
        <circle cx="19" cy="23" r="1.4" />
        <circle cx="28" cy="21.5" r="1.2" />
        <circle cx="23" cy="29" r="1.5" />
        <circle cx="30" cy="30" r="1.1" />
        <circle cx="18" cy="31.5" r="1" />
        <circle cx="26" cy="25.5" r="0.9" />
      </g>
      <circle cx="40" cy="38" r="16" fill="#9c3f2e" />
      <circle cx="40" cy="38" r="12.5" fill="#f4e8db" />
      <g fill="#b56a4a">
        <circle cx="35" cy="34" r="1.4" />
        <circle cx="44" cy="32.5" r="1.2" />
        <circle cx="39" cy="40" r="1.5" />
        <circle cx="46" cy="41" r="1.1" />
        <circle cx="34" cy="42.5" r="1" />
        <circle cx="42" cy="36.5" r="0.9" />
      </g>
    </svg>
  ),
  sut: (
    <svg viewBox="0 0 64 64">
      <path d="M24 8h16l6 12v32a3 3 0 0 1-3 3H21a3 3 0 0 1-3-3V20z" fill="#fbfcff" stroke="#d4dcec" strokeWidth="1.4" />
      <path d="M24 8h16l6 12H18z" fill="#eef2fa" stroke="#d4dcec" strokeWidth="1.4" />
      <path d="M27 8v12M37 8v12" stroke="#d4dcec" strokeWidth="1.2" />
      <rect x="18" y="30" width="28" height="13" fill="#3563c4" />
      <text x="32" y="39.5" textAnchor="middle" fontSize="8.5" fontWeight="700" fill="#ffffff" fontFamily="Sora, Inter, sans-serif">SÜT</text>
      <path d="M22 49.5c2.5-2 5.5-2 8 0s5.5 2 8 0" fill="none" stroke="#a9bce0" strokeWidth="1.6" strokeLinecap="round" />
    </svg>
  ),
  cikolata: (
    <svg viewBox="0 0 64 64">
      <rect x="22" y="7" width="20" height="8" rx="2.5" fill="#f4f1ea" stroke="#d8d2c4" strokeWidth="1.2" />
      <path d="M21 15h22c1.7 0 3 1.4 2.9 3.1-.2 4 .6 6.6 1.6 9.4 1 2.9 1.5 6 1.5 9.5 0 9.5-6 15-17 15S15 46.5 15 37c0-3.5.5-6.6 1.5-9.5 1-2.8 1.8-5.4 1.6-9.4-.1-1.7 1.2-3.1 2.9-3.1z" fill="#4a2f1e" />
      <path d="M17.5 32.5h29v13c-2.5 4.3-7.4 6.5-14.5 6.5s-12-2.2-14.5-6.5z" fill="#fdfbf6" />
      <text x="32" y="42" textAnchor="middle" fontSize="7" fontWeight="700" fill="#3d2817" fontFamily="Sora, Inter, sans-serif">nutella</text>
      <path d="M20 20.5c3.8 1.6 8 2.4 12 2.4s8.2-.8 12-2.4" fill="none" stroke="#5f3f29" strokeWidth="1.4" />
    </svg>
  ),
  ayran: (
    <svg viewBox="0 0 64 64">
      <path d="M20 14h24l-1.2 6H21.2z" fill="#e8edf6" stroke="#cfd8e8" strokeWidth="1.2" />
      <path d="M21.2 20h21.6L40 55a3 3 0 0 1-3 2.7H27A3 3 0 0 1 24 55z" fill="#fbfcff" stroke="#cfd8e8" strokeWidth="1.4" />
      <path d="M22.3 29h19.4l-1.1 13H23.4z" fill="#2f7fc1" />
      <text x="32" y="37.5" textAnchor="middle" fontSize="5.4" fontWeight="700" fill="#ffffff" fontFamily="Sora, Inter, sans-serif" textLength="15" lengthAdjust="spacingAndGlyphs">AYRAN</text>
      <path d="M38 14l4-8" stroke="#e0654f" strokeWidth="2.4" strokeLinecap="round" />
    </svg>
  ),
};

const heroProducts = [
  { name: "Torku Sucuk 400g", price: "5,99", oldPrice: "7,49", art: "sucuk" },
  { name: "Pınar Süt 1L", price: "0,89", oldPrice: "1,19", art: "sut" },
  { name: "Nutella 750g", price: "4,99", oldPrice: "6,29", art: "cikolata" },
  { name: "Sütaş Ayran 1L", price: "0,79", oldPrice: "0,99", art: "ayran" },
];

function useReveal() {
  useEffect(() => {
    const elements = document.querySelectorAll(".reveal");
    if (!("IntersectionObserver" in window)) {
      elements.forEach((el) => el.classList.add("is-visible"));
      return undefined;
    }
    const observer = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (entry.isIntersecting) {
            entry.target.classList.add("is-visible");
            observer.unobserve(entry.target);
          }
        });
      },
      { threshold: 0.15, rootMargin: "0px 0px -40px 0px" },
    );
    elements.forEach((el) => observer.observe(el));
    return () => observer.disconnect();
  }, []);
}

function useHeaderShadow() {
  const [scrolled, setScrolled] = useState(false);
  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 8);
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);
  return scrolled;
}

function BrochureMock() {
  return (
    <div className="landing-brochure" aria-hidden="true">
      <div className="landing-brochure-header">
        <div className="landing-brochure-brand">
          <span className="landing-brochure-logo">A</span>
          <span className="landing-brochure-brand-name">
            <strong>ANADOLU MARKET</strong>
            <small>Süpermarket &amp; Şarküteri</small>
          </span>
        </div>
        <span className="landing-brochure-burst">
          <strong>%40</strong>
          <small>'a varan indirim</small>
        </span>
      </div>
      <div className="landing-brochure-ribbon">
        <strong>HAFTANIN FIRSATLARI</strong>
        <span>08.07 – 14.07</span>
      </div>
      <div className="landing-brochure-grid">
        {heroProducts.map((product) => (
          <div key={product.name} className="landing-brochure-item">
            <span className="landing-brochure-figure">{productArt[product.art]}</span>
            <small>{product.name}</small>
            <span className="landing-brochure-prices">
              <s>{product.oldPrice}€</s>
              <span className="landing-brochure-price">
                {product.price}
                <small>€</small>
              </span>
            </span>
          </div>
        ))}
      </div>
      <div className="landing-brochure-footer">
        <span>Hauptstraße 12, Berlin</span>
        <span>Stoklarla sınırlıdır</span>
      </div>
    </div>
  );
}

function ChatMock() {
  return (
    <div className="landing-chat" aria-hidden="true">
      <div className="landing-chat-bubble landing-chat-user">
        Torku Sucuk 400g - 5.99€
        <br />
        Pınar Süt 1L - 0.89€
        <br />
        Nutella 750g - 4.99€
        <br />
        Sütaş Ayran 1L - 0.79€
      </div>
      <div className="landing-chat-slot">
        <div className="landing-chat-typing">
          <span />
          <span />
          <span />
        </div>
        <div className="landing-chat-bubble landing-chat-bot">
          <strong>LeafletPilot</strong>
          4 ürün eşleşti. Broşür önizlemeniz hazır ✅
        </div>
      </div>
    </div>
  );
}

export function Landing() {
  useReveal();
  const scrolled = useHeaderShadow();

  return (
    <div className="landing">
      <header className={`landing-header${scrolled ? " is-scrolled" : ""}`}>
        <a className="brand" href="#/">
          <span className="brand-mark">LP</span>
          <span>
            <strong>LeafletPilot</strong>
            <small>Broşür Otomasyonu</small>
          </span>
        </a>
        <nav className="landing-nav" aria-label="Sayfa içi gezinme">
          <a href="#nasil-calisir">Nasıl Çalışır</a>
          <a href="#ozellikler">Özellikler</a>
          <a href="#fiyatlar">Fiyatlar</a>
          <a href="#sss">SSS</a>
        </nav>
        <div className="landing-header-actions">
          <a className="landing-btn landing-btn-ghost" href="#/login">
            Giriş Yap
          </a>
          <a className="landing-btn landing-btn-primary" href="#/start">
            Ücretsiz Dene
          </a>
        </div>
      </header>

      <main>
        <section className="landing-hero">
          <div className="landing-hero-glow" aria-hidden="true" />
          <div className="landing-hero-copy">
            <span className="landing-eyebrow">Marketler için broşür otomasyonu</span>
            <h1>
              Ürün listenizi gönderin, kampanya broşürünüz{" "}
              <span className="landing-gradient-text">dakikalar içinde</span> hazır olsun
            </h1>
            <p>
              LeafletPilot; market, kasap ve şarküterilerin haftalık kampanya broşürlerini mesajlaşma uygulaması
              üzerinden otomatik hazırlar. Tasarım programı yok, saatlerce uğraş yok.
            </p>
            <div className="landing-hero-actions">
              <a className="landing-btn landing-btn-primary landing-btn-lg" href="#/start">
                İlk Broşürünüz Ücretsiz
              </a>
              <a className="landing-btn landing-btn-ghost landing-btn-lg" href="#nasil-calisir">
                Nasıl çalışır?
              </a>
            </div>
            <ul className="landing-hero-bullets">
              <li>Kurulum ücreti yok</li>
              <li>5 dakikada ilk taslak</li>
              <li>Baskı PDF'i + sosyal medya görseli</li>
            </ul>
          </div>
          <div className="landing-hero-visual">
            <ChatMock />
            <BrochureMock />
          </div>
        </section>

        <section className="landing-section landing-pain">
          <h2 className="reveal">Haftalık broşür hazırlamak neden bu kadar yorucu?</h2>
          <div className="landing-card-grid landing-card-grid-3">
            {painPoints.map((item, index) => (
              <article key={item.title} className="landing-card reveal" style={{ transitionDelay: `${index * 90}ms` }}>
                <h3>{item.title}</h3>
                <p>{item.text}</p>
              </article>
            ))}
          </div>
        </section>

        <section className="landing-section" id="nasil-calisir">
          <span className="landing-eyebrow reveal">Üç adım</span>
          <h2 className="reveal">Nasıl çalışır?</h2>
          <p className="landing-section-sub reveal">Panel öğrenmenize gerek yok. Her şey mesajlaşma uygulamanızdan.</p>
          <div className="landing-steps">
            {steps.map((step, index) => (
              <article key={step.title} className="landing-step reveal" style={{ transitionDelay: `${index * 110}ms` }}>
                <span className="landing-step-number">{index + 1}</span>
                <h3>{step.title}</h3>
                <p>{step.text}</p>
              </article>
            ))}
          </div>
        </section>

        <section className="landing-section" id="ozellikler">
          <span className="landing-eyebrow reveal">Özellikler</span>
          <h2 className="reveal">Broşürden fazlası</h2>
          <p className="landing-section-sub reveal">Kampanya operasyonunuzun tamamı tek sistemde.</p>
          <div className="landing-card-grid landing-card-grid-3">
            {features.map((feature, index) => (
              <article
                key={feature.title}
                className="landing-card reveal"
                style={{ transitionDelay: `${(index % 3) * 90}ms` }}
              >
                <span className="landing-card-icon">{featureIcons[feature.icon]}</span>
                <h3>{feature.title}</h3>
                <p>{feature.text}</p>
              </article>
            ))}
          </div>
        </section>

        <section className="landing-section" id="fiyatlar">
          <span className="landing-eyebrow reveal">Fiyatlar</span>
          <h2 className="reveal">Basit ve şeffaf fiyatlandırma</h2>
          <p className="landing-section-sub reveal">İlk broşürünüz ücretsiz. Beğenmezseniz ödeme yapmazsınız.</p>
          <div className="landing-pricing">
            {plans.map((plan, index) => (
              <article
                key={plan.name}
                className={`landing-plan reveal${plan.highlighted ? " landing-plan-highlighted" : ""}`}
                style={{ transitionDelay: `${index * 110}ms` }}
              >
                {plan.highlighted ? <span className="landing-plan-badge">En çok tercih edilen</span> : null}
                <h3>{plan.name}</h3>
                <div className="landing-plan-price">
                  {plan.price}
                  <small>/ay</small>
                </div>
                <p>{plan.tagline}</p>
                <ul>
                  {plan.items.map((item) => (
                    <li key={item}>{item}</li>
                  ))}
                </ul>
                <a className={`landing-btn landing-btn-lg ${plan.highlighted ? "landing-btn-primary" : "landing-btn-ghost"}`} href="#/start">
                  Ücretsiz Dene
                </a>
              </article>
            ))}
          </div>
        </section>

        <section className="landing-section" id="sss">
          <span className="landing-eyebrow reveal">SSS</span>
          <h2 className="reveal">Sık sorulan sorular</h2>
          <div className="landing-faq">
            {faqs.map((faq, index) => (
              <details key={faq.q} className="landing-faq-item reveal" style={{ transitionDelay: `${index * 60}ms` }}>
                <summary>{faq.q}</summary>
                <p>{faq.a}</p>
              </details>
            ))}
          </div>
        </section>

        <section className="landing-cta reveal">
          <h2>Bu haftanın kampanyasını LeafletPilot hazırlasın</h2>
          <p>Mevcut kampanya ürünlerinizle kısa bir demo hazırlayalım. İlk broşürünüz bizden.</p>
          <a className="landing-btn landing-btn-cta landing-btn-lg" href="#/start">
            İlk Broşürünüz Ücretsiz
          </a>
        </section>
      </main>

      <footer className="landing-footer">
        <a className="brand" href="#/">
          <span className="brand-mark">LP</span>
          <span>
            <strong>LeafletPilot</strong>
            <small>Broşür Otomasyonu</small>
          </span>
        </a>
        <p>Yerel marketler için haftalık kampanya broşürü üretim sistemi.</p>
        <small>© {new Date().getFullYear()} LeafletPilot · iletisim@leafletpilot.com</small>
      </footer>
    </div>
  );
}
