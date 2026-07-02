# LeafletPilot — AI Destekli Market Broşür Otomasyonu — Tasarım Dokümantasyon Paketi

Bu paket, AI destekli haftalık market broşür otomasyonu uygulamasının arayüz tasarımına başlamak için hazırlanmıştır.

Ürün konumlandırması:

> Marketler, kasaplar, şarküteriler ve yerel gıda işletmeleri için mesajlaşma uygulaması üzerinden kampanya listesi alıp otomatik broşür, PDF ve sosyal medya görselleri üreten SaaS platformu.

İlk tasarım dili, DisKlinikCRM ve Comptario çizgisine yakın olmalıdır:

- Modern B2B SaaS görünümü
- Güven veren kurumsal yapı
- Temiz beyaz/zincirli gri arka planlar
- Lacivert / mavi tabanlı ana renkler
- Yumuşak kartlar
- Net tablo ve form yapısı
- Az ama güçlü vurgu renkleri
- Mobil uyumlu dashboard mantığı
- Operasyonel kullanımda hızlı aksiyon odaklı UI

## Paket İçeriği

1. `01_PRODUCT_BRIEF.md`  
   Ürün fikri, hedef kullanıcı, değer önerisi ve MVP özeti.

2. `02_DESIGN_SYSTEM.md`  
   Renkler, tipografi, spacing, radius, shadow, layout ve genel UI dili.

3. `03_INFORMATION_ARCHITECTURE.md`  
   Sayfa yapısı, menü ağacı ve modül organizasyonu.

4. `04_USER_FLOWS.md`  
   Telegram/WhatsApp kampanya gönderim akışı, admin akışı, onay akışı.

5. `05_SCREEN_REQUIREMENTS.md`  
   Her ekran için detaylı arayüz gereksinimleri.

6. `06_COMPONENT_GUIDELINES.md`  
   Kartlar, tablolar, butonlar, badge’ler, formlar, empty state ve modal kuralları.

7. `07_DASHBOARD_UI_SPEC.md`  
   Ana dashboard ekranının metrikleri, kartları ve kampanya durumu.

8. `08_MESSAGING_BOT_FLOW.md`  
   Telegram/WhatsApp bot konuşma akışları ve mesaj metinleri.

9. `09_BROCHURE_TEMPLATE_SPEC.md`  
   Broşür şablonları, sayfa yapısı, ürün kartı mantığı ve çıktı formatları.

10. `10_ADMIN_PANEL_SPEC.md`  
   Ürün, kategori, marka, şablon, kampanya ve kullanıcı yönetimi.

11. `11_MVP_SCOPE.md`  
   MVP kapsamı, sonraya bırakılacak özellikler ve faz planı.

12. `12_COPY_I18N.md`  
   UI metinleri, boş durum mesajları, hata mesajları ve mikro metinler.

13. `13_DESIGN_AGENT_PROMPT.md`  
   Figma/UI tasarım agent’ına veya geliştiriciye verilecek hazır prompt.

## Tasarım Önceliği

İlk hedef, tüm sistemi tasarlamak değil; şu üç ana deneyimi netleştirmektir:

1. Market sahibi ürün listesini mesajlaşma uygulaması üzerinden gönderir.
2. Sistem ürünleri eşleştirir ve broşür taslağı üretir.
3. Yönetici panelinden kampanya, ürün ve şablon yönetilir.

## Önerilen İlk Tasarım Seti

Öncelikli ekranlar:

1. Login
2. Dashboard
3. Kampanyalar Listesi
4. Kampanya Detayı / Önizleme
5. Yeni Kampanya Oluştur
6. Ürün Kataloğu
7. Ürün Ekle / Düzenle
8. Şablonlar
9. Müşteri / Market Ayarları
10. Bot Bağlantıları
11. Ayarlar

## Not

Bu dokümanlarda verilen renkler öneridir. DisKlinikCRM veya Comptario’daki gerçek renk paleti farklıysa, sadece `02_DESIGN_SYSTEM.md` dosyasındaki renk paleti güncellenerek tüm tasarım dili korunabilir.


## Marka Kararı

Bu pakette proje adı **LeafletPilot** olarak güncellenmiştir.

Önerilen marka kullanımı:

```txt
LeafletPilot
AI-powered leaflet and brochure automation for local markets
```

Türkçe konumlandırma:

```txt
LeafletPilot, yerel marketlerin ürün listelerini otomatik olarak kampanya broşürlerine, PDF dosyalarına ve sosyal medya görsellerine dönüştüren AI destekli bir SaaS platformudur.
```
