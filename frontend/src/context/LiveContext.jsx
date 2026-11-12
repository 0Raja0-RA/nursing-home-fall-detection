import { createContext, useContext } from 'react';
import { useWebSocket } from '../hooks/useWebSocket';
import { useRingkasan } from '../hooks/useRingkasan';
import { WS_URL } from '../config';

// Satu koneksi WebSocket untuk seluruh dashboard. Dulu tiap halaman membuka
// koneksinya sendiri, sehingga banner alarm hanya ada di halaman tertentu.
const LiveContext = createContext({
    cameraData: {}, alerts: [], connected: false, dismissAlert: () => {}, perbaruiAlert: () => {},
    ringkasan: null, segarkanRingkasan: () => {},
});

export function LiveProvider({ children }) {
    const live = useWebSocket(WS_URL);
    const { ringkasan, segarkanRingkasan } = useRingkasan(live.alerts.length);
    return (
        <LiveContext.Provider value={{ ...live, ringkasan, segarkanRingkasan }}>
            {children}
        </LiveContext.Provider>
    );
}

export const useLive = () => useContext(LiveContext);
