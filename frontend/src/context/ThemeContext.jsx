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

    return (
        <ThemeContext.Provider value={{ darkMode, setDarkMode, toggleTheme }}>
            {children}
        </ThemeContext.Provider>
    );
}

export const useTheme = () => useContext(ThemeContext);