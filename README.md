mulai dengan mengetik "ssh -N -L 18001:127.0.0.1:8001 engineer@10.10.100.124" di cmd, setelah memasukan sandi ssh biarkan layar cmd tetap terbuka lalu buka website "http://127.0.0.1:18001/" setelah itu buka website "http://10.10.100.124:8000" dan pastikan menggunakan twingate atau wifi sekolah secara langsng untuk membuka website ini

fungsi website pertama adalah sebagai dashboard dari semua fitur yg kami sampai kan, dan fungsi website ke 2 adalah sebagai website pengirim traffic

jika ingin lebih mudah lagi bisa dengan menekan file bernama "RUN_IDS.bat" di folder project, setelah di klik akan melakukan pengecekan sebentar, setelah itu muncul 2 jendela baru yang berisi website utama dan website pengirim traffic untuk ip domain nya "http://127.0.0.1:8001" web dashboard utama dan "http://127.0.0.1:8000" untuk mengirim traffic
