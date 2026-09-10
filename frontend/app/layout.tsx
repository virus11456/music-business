import type { Metadata } from 'next';
import './globals.css';
export const metadata: Metadata={title:'SIMPLES｜唱片工作室',description:'日本壓片選品、行情與進貨決策工作台'};
export default function RootLayout({children}:{children:React.ReactNode}){return <html lang="zh-Hant"><body>{children}</body></html>}
