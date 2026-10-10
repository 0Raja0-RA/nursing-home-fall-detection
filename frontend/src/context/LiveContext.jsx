import { createContext, useContext } from 'react';
import { useWebSocket } from '../hooks/useWebSocket';
import { WS_URL } from '../config';

// Satu koneksi WebSocket untuk seluruh dashboard. Dulu tiap halaman membuka
// koneksinya sendiri, sehingga banner alarm hanya ada di halaman tertentu.
const LiveContext = createContext({
    cameraData: {}, alerts: [], connected: false, dismissAlert: () => {},
});

export function LiveProvider({ children }) {
    const live = useWebSocket(WS_URL);
    return <LiveContext.Provider value={live}>{children}</LiveContext.Provider>;
}

export const useLive = () => useContext(LiveContext);
