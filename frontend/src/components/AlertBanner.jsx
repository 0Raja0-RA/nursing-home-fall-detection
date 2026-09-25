import React from 'react';

export default function AlertBanner({ alertData, onDismiss }) {
    if (!alertData) return null;

    return (
        <div className="fixed inset-0 bg-red-600 z-50 flex flex-col items-center justify-center text-white p-4 text-center">
            <span className="text-9xl mb-4 animate-bounce">⚠️</span>
            <h1 className="text-5xl md:text-7xl font-bold mb-4 tracking-wider">
                PERINGATAN DARURAT
            </h1>
            <p className="text-3xl md:text-4xl mb-12">
                Kejadian Jatuh Terdeteksi di: <br />
                <span className="font-extrabold text-yellow-300">{alertData.camera_location || 'Lokasi Tidak Diketahui'}</span>
            </p>
            <button
                onClick={onDismiss}
                className="bg-white text-red-700 px-10 py-5 rounded-full text-2xl font-bold shadow-xl hover:bg-gray-200 transition transform hover:scale-105"
            >
                TINDAK LANJUTI
            </button>
        </div>
    );
}