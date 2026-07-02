# User Flows

## Flow 1 — Mesajlaşma Uygulamasıyla Kampanya Oluşturma

Ana hedef: Market sahibi panel açmadan kampanya broşürü oluşturabilmeli.

### Adımlar

1. Kullanıcı Telegram/WhatsApp botuna mesaj atar.
2. Bot kullanıcıyı tanır.
3. Kullanıcı ürün listesini gönderir.
4. Sistem listeyi analiz eder.
5. Sistem ürün adlarını ve fiyatları ayıklar.
6. Sistem ürünleri katalogla eşleştirir.
7. Eksik veya düşük güvenli ürün varsa kullanıcıya bildirir.
8. Sistem varsayılan şablonla önizleme üretir.
9. Kullanıcı önizlemeyi kontrol eder.
10. Kullanıcı onaylar veya düzeltme ister.
11. Sistem final PDF/PNG dosyalarını üretir.
12. Dosyalar kullanıcıya gönderilir.
13. Kampanya panelde tamamlandı olarak görünür.

### Bot Mesaj Örneği

Kullanıcı:

```txt
Coca Cola 2L - 1.59€
Eti Burçak - 0.99€
Torku Sucuk 400g - 5.99€
Ülker Halley - 1.49€
```

Bot:

```txt
Kampanya listenizi aldım. 4 ürünü analiz ediyorum.
```

Bot:

```txt
4 ürün bulundu.
3 ürün güvenli şekilde eşleşti.
1 ürün için kontrol gerekiyor: Torku Sucuk 400g

Önizleme hazırlamamı ister misiniz?
```

Kullanıcı:

```txt
Evet
```

Bot:

```txt
Broşür taslağınız hazır. Lütfen ürünleri ve fiyatları kontrol edin.

[Önizleme PNG]

Onaylıyor musunuz?
```

Butonlar:

- Onayla
- Fiyat Düzelt
- Ürün Değiştir
- İptal Et

## Flow 2 — Excel ile Kampanya Oluşturma

1. Kullanıcı Excel dosyası gönderir.
2. Sistem dosyayı okur.
3. Kolonları tahmin eder:
   - ürün adı
   - fiyat
   - eski fiyat
   - barkod
   - kategori
4. Kullanıcıdan kolon onayı istenir.
5. Ürünler eşleştirilir.
6. Önizleme oluşturulur.
7. Kullanıcı onaylar.
8. Final çıktılar gönderilir.

### Excel Kolon Onay Mesajı

```txt
Excel dosyanızı okudum.

Tahmin edilen kolonlar:
- Ürün Adı: A sütunu
- Fiyat: B sütunu
- Barkod: C sütunu

Devam edeyim mi?
```

## Flow 3 — Panelden Yeni Kampanya Oluşturma

1. Kullanıcı “Yeni Kampanya” butonuna tıklar.
2. Kampanya adını girer.
3. Market/şube seçer.
4. Şablon seçer.
5. Ürünleri manuel ekler veya liste yapıştırır.
6. Sistem ürünleri eşleştirir.
7. Kullanıcı eksik ürünleri düzeltir.
8. Önizleme oluşturulur.
9. Final dosyalar üretilir.

## Flow 4 — Eksik Ürün Yönetimi

1. Sistem ürün bulamaz.
2. Kampanya detayında “Eksik Ürünler” bölümü görünür.
3. Kullanıcı şu seçeneklerden birini seçer:
   - Var olan ürüne bağla
   - Yeni ürün oluştur
   - Ürünü kampanyadan çıkar
   - Görselsiz metin kartı olarak kullan
4. Seçim sonrası sistem kampanyayı yeniden oluşturur.

## Flow 5 — Yeni Ürün Ekleme

1. Kullanıcı ürün adını girer.
2. Marka seçer veya yeni marka ekler.
3. Kategori seçer.
4. Barkod girer.
5. PNG ürün görseli yükler.
6. Alternatif isimler ekler.
7. Ürünü kaydeder.
8. Sistem ürünü onaylı katalog öğesi olarak kullanır.

## Flow 6 — Şablon Seçimi

1. Kullanıcı kampanya oluştururken şablon seçer.
2. Şablon kartlarında şunlar görünür:
   - Önizleme
   - Formatlar
   - Ürün kapasitesi
   - Kullanım amacı
3. Kullanıcı şablonu seçer.
4. Sistem ürün sayısına göre sayfa sayısını hesaplar.
5. Gerekirse kullanıcıya uyarı verir.

## Flow 7 — Önizleme ve Onay

Her kampanya finalden önce onay gerektirir.

Önizleme ekranında:

- Broşür görüntüsü
- Ürün listesi
- Fiyatlar
- Eksik ürünler
- Düşük güvenli eşleşmeler
- Çıktı formatları
- Onay butonu
- Revizyon iste butonu

Onay sonrası:

- PDF oluşturulur
- PNG oluşturulur
- Dosyalar kaydedilir
- Bot üzerinden kullanıcıya gönderilir

## Flow 8 — Concierge MVP Akışı

İlk müşterilerde bazı işlemler manuel olabilir.

1. Kullanıcı listeyi gönderir.
2. Sistem otomatik parse eder.
3. İç ekip eksik ürünleri manuel eşleştirir.
4. Broşür taslağı üretilir.
5. Kullanıcıya otomatik bot mesajıyla gönderilir.
6. Kullanıcı sistemi tam otomatik deneyim olarak algılar.

Bu akış, ürün-pazar uyumunu hızlı test etmek için uygundur.
