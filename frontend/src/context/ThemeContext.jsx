import { createContext, useContext, useState, useEffect } from 'react';

const ThemeContext = createContext();

export function ThemeProvider({ children }) {
    // 1. Baca dari localStorage, jika kosong default ke true (dark mode)
    const [darkMode, setDarkMode] = useState(() => {
        const saved = localStorage.getItem('theme');
        if (saved !== null) {
            return JSON.parse(saved);
        }
        return true; // Default awal gelap
    });

    useEffect(() => {
        const root = document.documentElement;
        if (darkMode) {
            root.classList.add('dark');
            localStorage.setItem('theme', JSON.stringify(true));
        } else {
            root.classList.remove('dark');
            localStorage.setItem('theme', JSON.stringify(false));
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