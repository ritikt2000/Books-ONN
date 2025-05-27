from flask import Flask, render_template, request
import numpy as np
import joblib

popular_df = joblib.load('popular.joblib')
pt = joblib.load('pt.joblib')
books = joblib.load('books.joblib')
similarity_scores = joblib.load('similarity_scores.joblib')

# popular_df = pickle.load(open('popular.pkl','rb'))
# pt = pickle.load(open('pt.pkl','rb'))
# books = pickle.load(open('books.pkl','rb'))
# similarity_scores = pickle.load(open('similarity_scores.pkl','rb'))

app = Flask(__name__)


@app.route('/')
def index():
    return render_template('index.html',
                           book_name=list(popular_df['Book-Title'].values),
                           author=list(popular_df['Book-Author'].values),
                           image=list(popular_df['Image-URL-M'].values),
                           votes=list(popular_df['num_ratings'].values),
                           rating=list(popular_df['avg_rating'].values)
                           )


@app.route('/recommend')
def recommend_ui():
    # Pass an empty user_input_value initially for the recommend page
    return render_template('recommend.html', user_input_value='')


@app.route('/recommend_books', methods=['post'])
def recommend():
    user_input = request.form.get('user_input')
    data = []
    error_message = None

    try:
        # Find the index of the book in the pivot table
        # np.where returns a tuple of arrays; we need the first element of the first array
        indices = np.where(pt.index == user_input)[0]

        if len(indices) == 0:
            # Book not found
            error_message = f"Book '{user_input}' not found. Please check the title and try again."
        else:
            index = indices[0]
            # Get similarity scores and sort them
            similar_items = sorted(list(enumerate(similarity_scores[index])), key=lambda x: x[1], reverse=True)[
                            1:5]  # Get top 4 similar books

            if not similar_items:
                error_message = f"No recommendations found for '{user_input}'. Try a different book."
            else:
                for i in similar_items:
                    item = []
                    # pt.index[i[0]] is the title of the similar book
                    book_title_recommended = pt.index[i[0]]
                    temp_df = books[books['Book-Title'] == book_title_recommended]

                    # Ensure we get unique entries and the book exists
                    if not temp_df.empty:
                        # Use drop_duplicates to get a single entry for the book
                        unique_book_entry = temp_df.drop_duplicates('Book-Title')
                        item.extend(list(unique_book_entry['Book-Title'].values))
                        item.extend(list(unique_book_entry['Book-Author'].values))
                        item.extend(list(unique_book_entry['Image-URL-M'].values))
                        data.append(item)
                    else:
                        # This case should ideally not happen if pt.index is derived from books.pkl
                        print(f"Warning: Recommended book '{book_title_recommended}' not found in books DataFrame.")

                if not data and not error_message:  # If similar items were found, but no data could be populated (e.g. all lookups failed)
                    error_message = f"Found recommendations for '{user_input}', but had trouble fetching their details. Please try again."


    except Exception as e:
        # Catch any other unexpected errors during the recommendation process
        print(f"An unexpected error occurred: {e}")  # Log error for debugging
        error_message = "An unexpected error occurred while fetching recommendations. Please try again."
        data = []  # Ensure data is empty if an error occurs

    # print(data) # For debugging

    return render_template('recommend.html', data=data, error_message=error_message, user_input_value=user_input)


@app.route('/about')
def about():
    return render_template('about.html')


if __name__ == '__main__':
    app.run(debug=True)