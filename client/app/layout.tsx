import "./globals.css";

export const metadata = {
  title: "AirMouse",
  description: "Use your phone as a desk mouse",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}

