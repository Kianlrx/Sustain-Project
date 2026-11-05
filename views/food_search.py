# Food search results page.
# Placeholder.
import streamlit as st

def render_food_search_page(query):
    st.title("Search results")
    st.caption(f'Results for "{query}"')
    st.info("Food search results will appear here once the search is built.")
    if st.button("Back to diary"):
        del st.session_state.food_search
        st.rerun()