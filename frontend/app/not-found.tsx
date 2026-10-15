import Link from "next/link";

export default function NotFound() {
  return (
    <>
      <h1>Page not found</h1>
      <p className="lede">
        There is nothing at this address. <Link href="/">Go to Compare</Link>.
      </p>
    </>
  );
}
