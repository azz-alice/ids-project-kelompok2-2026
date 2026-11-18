# Network Sensor

Menggunakan Scapy `AsyncSniffer` untuk menangkap metadata paket dari interface yang dipilih. Pada Windows, packet capture membutuhkan Npcap yang dapat digunakan Scapy.

Sensor mencatat interface, timestamp, source/destination IP, protocol, port, panjang paket, dan TCP flags jika tersedia. Sensor hanya dapat mengamati paket yang terlihat pada interface tersebut. Status capture tidak boleh ditampilkan aktif sebelum proses sniffing benar-benar berjalan.
