import { createContext, useContext, useState, useEffect } from 'react';

const ThemeContext = createContext();

export function ThemeProvider({ children }) {
    // Tema gelap kecuali pengguna pernah memilih terang. Penyimpanan browser yang diblokir
    // tidak boleh menggagalkan aplikasi. Skrip kecil di index.html membaca kunci yang sama
    // sebelum halaman digambar, supaya tema gelap tidak diawali kilatan terang.
    const [darkMode, setDarkMode] = useState(() => {
        try {
            return localStorage.getItem('theme') !== 'false';
        } catch {
            return true;
        }
    });

    useEffect(() => {
        document.documentElement.classList.toggle('dark', darkMode);
        // Bilah status dan bilah alamat browser HP mengikuti warna bilah atas dashboard.
        document.querySelector('meta[name="theme-color"]')?.setAttribute('content', darkMode ? '#0f172b' : '#ffffff');
        try {
            localStorage.setItem('theme', JSON.stringify(darkMode));
        } catch {
            // Penyimpanan browser diblokir: pilihan berlaku sampai halaman ditutup.
        }
    }, [darkMode]);

    // Fungsi toggle yang aman untuk mengubah status secara manual
    const toggleTheme = () => {
        setDarkMode(prev => !prev);
    };

    // Teks besar per perangkat (prinsip 10 di docs/architecture.md): kelas .teks-besar di <html>
    // menaikkan text-xs ke 14 px dan text-sm ke 16 px. Disimpan di browser seperti tema.
    const [teksBesar, setTeksBesar] = useState(() => {
        try {
            return localStorage.getItem('teks-besar') === 'true';
        } catch {
            return false;
        }
    });

    useEffect(() => {
        document.documentElement.classList.toggle('teks-besar', teksBesar);
        try {
            localStorage.setItem('teks-besar', String(teksBesar));
        } catch {
            // Penyimpanan browser diblokir: pilihan berlaku sampai halaman ditutup.
        }
    }, [teksBesar]);

    return (
        <ThemeContext.Provider value={{ darkMode, setDarkMode, toggleTheme, teksBesar, setTeksBesar }}>
            {children}
        </ThemeContext.Provider>
    );
}

export const useTheme = () => useContext(ThemeContext);